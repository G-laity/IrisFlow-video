"""合成器 REST + SSE 路由（/api/composer）。

M1：素材库（assets* 全套 + 上传）+ status-stream SSE 骨架 + 配置与 ffmpeg 探测。
M2/M3：projects / renders 端点按里程碑扩展。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from composer import config as composer_config
from composer import assets as composer_assets
from composer import ffmpeg as composer_ffmpeg
from composer.store import composer_store
from llm.constants import (
    COMPOSER_KIND_AUDIO,
    COMPOSER_KIND_IMAGE,
    COMPOSER_KIND_VIDEO,
    COMPOSER_MEDIA_EXTS,
    COMPOSER_SSE_ASSET,
    COMPOSER_SSE_CONNECTED,
    COMPOSER_SSE_HEARTBEAT,
    COMPOSER_STREAM_CHUNK,
    SSE_MEDIA_TYPE,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/composer", tags=["composer"])

# ── SSE 订阅（广播模式：所有连接收到全部 composer 事件）─────

_subscribers: list[asyncio.Queue[dict[str, object]]] = []


async def broadcast_asset(event_type: str, asset: dict[str, object]) -> None:
    """素材变更广播（入库 / 删除）。"""
    event: dict[str, object] = {"type": COMPOSER_SSE_ASSET, "event": event_type, "asset": asset}
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def _iso_asset(asset: dict[str, object]) -> dict[str, object]:
    """素材字典 → 响应形态（created_at 转 ISO）。"""
    out = dict(asset)
    ts = out.get("created_at")
    if isinstance(ts, (int, float)):
        from datetime import datetime, timezone
        out["created_at"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return out


def _http_error(exc: Exception) -> HTTPException:
    """业务异常 → HTTP 错误（用户可读信息）。"""
    msg = str(exc) or "操作失败"
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=msg)
    return HTTPException(status_code=500, detail=msg)


# ── 素材库 ────────────────────────────────────────────────


class ImportRequest(BaseModel):
    url: str = Field(description="素材 URL（http/https）")
    kind: str | None = Field(default=None, description="类型提示：image / video / audio，可省略")


@router.get("/assets")
async def list_assets(kind: str | None = None):
    """素材列表（kind 过滤：image / video / audio）。"""
    if kind is not None and kind not in (COMPOSER_KIND_IMAGE, COMPOSER_KIND_VIDEO, COMPOSER_KIND_AUDIO):
        raise HTTPException(status_code=400, detail=f"无效的素材类型: {kind}")
    assets = await composer_store.list_assets(kind)
    return {"assets": [_iso_asset(a) for a in assets]}


@router.post("/assets")
async def import_asset_url(req: ImportRequest):
    """从 URL 拉取素材入库（下载 + hash 去重 + ffprobe 探测）。"""
    try:
        asset, duplicated = await composer_assets.import_from_url(req.url, req.kind)
    except (ValueError, RuntimeError) as e:
        raise _http_error(e) from None
    warnings: list[str] = []
    if not composer_ffmpeg.ffprobe_available:
        warnings.append(composer_ffmpeg.last_probe_error)
    await broadcast_asset("created", _iso_asset(asset))
    return {"asset": _iso_asset(asset), "duplicated": duplicated, "warnings": warnings}


@router.post("/assets/upload")
async def upload_asset(file: UploadFile = File(...)):
    """本地文件上传入库（独立于聊天上传，上限 500 MB，仅媒体类型）。"""
    try:
        asset, duplicated = await composer_assets.import_from_upload(file, file.filename or "")
    except (ValueError, RuntimeError) as e:
        raise _http_error(e) from None
    warnings: list[str] = []
    if not composer_ffmpeg.ffprobe_available:
        warnings.append(composer_ffmpeg.last_probe_error)
    await broadcast_asset("created", _iso_asset(asset))
    return {"asset": _iso_asset(asset), "duplicated": duplicated, "warnings": warnings}


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str):
    """素材详情（含 probe 探测元数据）。"""
    asset = await composer_store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return _iso_asset(asset)


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: str):
    """删除素材（引用计数归零才删文件）。"""
    try:
        deleted = await composer_assets.delete_asset(asset_id)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    if deleted is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    await broadcast_asset("deleted", {"asset_id": asset_id})
    return {"ok": True, "deleted": asset_id}


# ── 素材文件流（Range 支持，供预览播放）────────────────────

_RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


def _content_type_for(asset: dict[str, object]) -> str:
    ext = Path(str(asset.get("file_path", ""))).suffix.lower()
    entry = COMPOSER_MEDIA_EXTS.get(ext)
    if entry:
        return entry[1]
    kind = asset.get("kind")
    return {COMPOSER_KIND_IMAGE: "image/png", COMPOSER_KIND_VIDEO: "video/mp4", COMPOSER_KIND_AUDIO: "audio/mpeg"}.get(str(kind), "application/octet-stream")


@router.get("/assets/{asset_id}/file")
async def stream_asset_file(asset_id: str, request: Request):
    """素材流式播放（支持 HTTP Range，供视频预览 / 音频试听）。"""
    asset = await composer_store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    path = composer_assets.asset_abs_path(str(asset["file_path"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="素材文件缺失")

    size = path.stat().st_size
    content_type = _content_type_for(asset)
    range_header = request.headers.get("range")

    def _chunk_stream(start: int, end: int) -> AsyncIterator[bytes]:
        async def _gen():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(COMPOSER_STREAM_CHUNK, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        return _gen()

    if not range_header:
        headers = {
            "Content-Length": str(size),
            "Content-Type": content_type,
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
        }
        return StreamingResponse(_chunk_stream(0, size - 1), headers=headers)

    match = _RANGE_PATTERN.match(range_header.strip())
    if not match:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    start_s, end_s = match.group(1), match.group(2)
    if not start_s and not end_s:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    if not start_s:
        # 后缀范围：bytes=-N → 最后 N 字节
        suffix = int(end_s)
        if suffix <= 0:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
        if start >= size or end < start:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        end = min(end, size - 1)

    headers = {
        "Content-Length": str(end - start + 1),
        "Content-Type": content_type,
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
    }
    return StreamingResponse(_chunk_stream(start, end), status_code=206, headers=headers)


# ── SSE 状态流 ────────────────────────────────────────────


@router.get("/status-stream")
async def composer_status_stream():
    """合成器事件流（SSE）：素材入库 / 删除实时推送，心跳 15s。"""
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    _subscribers.append(queue)

    async def _stream():
        try:
            # 连接快照
            total = len(await composer_store.list_assets())
            yield f"data: {json.dumps({'type': COMPOSER_SSE_CONNECTED, 'asset_count': total})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=COMPOSER_SSE_HEARTBEAT)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # 心跳保活注释
        except GeneratorExit:
            pass
        finally:
            if queue in _subscribers:
                _subscribers.remove(queue)

    return StreamingResponse(_stream(), media_type=SSE_MEDIA_TYPE)


# ── 配置与探测 ────────────────────────────────────────────


@router.get("/config")
async def get_config():
    """合成器配置 + ffmpeg 探测结果。"""
    return {
        "config": composer_config.snapshot(),
        **composer_ffmpeg.availability_snapshot(),
    }


@router.put("/config")
async def put_config(updates: dict[str, object]):
    """更新合成器配置（ffmpeg 路径变更后立即重新探测）。"""
    snapshot = composer_config.apply(updates)
    await composer_ffmpeg.refresh_availability(str(snapshot.get("ffmpeg_path", "")))
    return {
        "config": snapshot,
        **composer_ffmpeg.availability_snapshot(),
    }
