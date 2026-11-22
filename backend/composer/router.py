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
from composer import music as composer_music
from composer import timeline as composer_timeline
from composer import tts as composer_tts
from composer.queue import render_queue
from composer.store import composer_store
from llm.constants import (
    COMPOSER_KIND_AUDIO,
    COMPOSER_KIND_IMAGE,
    COMPOSER_KIND_VIDEO,
    COMPOSER_MEDIA_EXTS,
    COMPOSER_SOURCE_MUSIC,
    COMPOSER_SOURCE_TTS,
    COMPOSER_SSE_ASSET,
    COMPOSER_SSE_CONNECTED,
    COMPOSER_SSE_HEARTBEAT,
    COMPOSER_SSE_PROGRESS,
    COMPOSER_SSE_PROJECT,
    COMPOSER_SSE_RENDER,
    COMPOSER_SSE_WARN,
    COMPOSER_STREAM_CHUNK,
    MSG_MUSIC_UNAVAILABLE,
    MSG_RENDER_NOT_FOUND,
    MSG_TTS_UNAVAILABLE,
    RENDER_COMPLETED,
    SSE_MEDIA_TYPE,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/composer", tags=["composer"])

# ── SSE 订阅（广播模式：所有连接收到全部 composer 事件）─────

_subscribers: list[asyncio.Queue[dict[str, object]]] = []


async def broadcast_asset(event_type: str, asset: dict[str, object]) -> None:
    """素材变更广播（入库 / 删除）。"""
    event: dict[str, object] = {"type": COMPOSER_SSE_ASSET, "event": event_type, "asset": asset}
    _broadcast(event)


async def broadcast_project(event_type: str, project: dict[str, object]) -> None:
    """项目变更广播（创建 / 更新 / 删除）。"""
    event: dict[str, object] = {"type": COMPOSER_SSE_PROJECT, "event": event_type, "project": project}
    _broadcast(event)


def _iso_render(render: dict[str, object]) -> dict[str, object]:
    out = dict(render)
    for key in ("created_at", "finished_at"):
        ts = out.get(key)
        if isinstance(ts, (int, float)):
            from datetime import datetime, timezone
            out[key] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return out


def _merged_render(render: dict[str, object]) -> dict[str, object]:
    """DB 行 + 内存 live 进度（状态迁移外的进度只驻内存）。"""
    live = render_queue.live_snapshot(str(render["render_id"]))
    merged = dict(render)
    if live:
        merged.update(live)
    return _iso_render(merged)


async def broadcast_render(render_id: str, live: dict[str, object] | None) -> None:
    """渲染状态迁移广播（queue 调用）。"""
    render = await composer_store.get_render(render_id)
    if render is None:
        return
    merged = dict(render)
    if live:
        merged.update(live)
    _broadcast({"type": COMPOSER_SSE_RENDER, "render": _iso_render(merged)})


async def broadcast_progress(
    render_id: str, progress: float, state: str, stage_detail: object
) -> None:
    """渲染进度广播（1s 节流，queue 调用）。"""
    _broadcast({
        "type": COMPOSER_SSE_PROGRESS,
        "render_id": render_id,
        "progress": progress,
        "state": state,
        "stage_detail": stage_detail,
    })


async def broadcast_warn(message: str) -> None:
    """合成器告警广播（磁盘水位等）。"""
    _broadcast({"type": COMPOSER_SSE_WARN, "message": message})


def _broadcast(event: dict[str, object]) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def iso_asset(asset: dict[str, object]) -> dict[str, object]:
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
    return {"assets": [iso_asset(a) for a in assets]}


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
    await broadcast_asset("created", iso_asset(asset))
    return {"asset": iso_asset(asset), "duplicated": duplicated, "warnings": warnings}


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
    await broadcast_asset("created", iso_asset(asset))
    return {"asset": iso_asset(asset), "duplicated": duplicated, "warnings": warnings}


class TTSDialogueSegment(BaseModel):
    text: str = Field(description="该句文本")
    voice: str | None = Field(default=None, description="该句音色，空 = 默认")


class TTSRequest(BaseModel):
    text: str | None = Field(default=None, description="待合成文本（与 segments 二选一）")
    segments: list[TTSDialogueSegment] | None = Field(
        default=None, description="多说话人对话片段（与 text 二选一）"
    )
    voice: str | None = Field(default=None, description="命名音色，空 = 配置默认")
    speed: float | None = Field(default=None, description="语速倍率，默认 1.0")
    split: bool = Field(default=True, description="长文本是否自动分句合成")


@router.post("/assets/tts")
async def generate_tts(req: TTSRequest):
    """语音合成并入库（source=tts）。支持长文本分句与多说话人 segments。"""
    text = (req.text or "").strip()
    if not text and not req.segments:
        raise HTTPException(status_code=400, detail="text 与 segments 至少提供一个")
    try:
        if req.segments:
            data, ext, provider = await composer_tts.synthesize_dialogue(
                [seg.model_dump() for seg in req.segments], req.speed
            )
            meta_text = f"[dialogue:{len(req.segments)}]"
        else:
            data, ext, provider = await composer_tts.synthesize(
                text, req.voice, req.speed, split=req.split
            )
            meta_text = text[:200]
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"{MSG_TTS_UNAVAILABLE}（{e}）") from None
    try:
        asset, duplicated = await composer_assets.import_from_bytes(
            data, f".{ext}", COMPOSER_SOURCE_TTS,
            meta={"model": provider, "voice": req.voice or "", "text": meta_text},
        )
    except (ValueError, RuntimeError) as e:
        raise _http_error(e) from None
    await broadcast_asset("created", iso_asset(asset))
    return {"asset": iso_asset(asset), "duplicated": duplicated, "provider": provider}


class MusicRequest(BaseModel):
    style: str = Field(description="风格 / 情绪描述")
    duration: int | None = Field(default=None, description="时长（秒），默认配置值")


@router.post("/assets/music")
async def generate_music(req: MusicRequest):
    """BGM 生成并入库（source=music）。服务不可用时返回 503 + 引导信息。"""
    try:
        data, ext = await composer_music.generate(req.style, req.duration)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"{MSG_MUSIC_UNAVAILABLE}（{e}）") from None
    try:
        asset, duplicated = await composer_assets.import_from_bytes(
            data, f".{ext}", COMPOSER_SOURCE_MUSIC,
            meta={"prompt": req.style, "duration": req.duration or 0},
        )
    except (ValueError, RuntimeError) as e:
        raise _http_error(e) from None
    await broadcast_asset("created", iso_asset(asset))
    return {"asset": iso_asset(asset), "duplicated": duplicated}


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str):
    """素材详情（含 probe 探测元数据）。"""
    asset = await composer_store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return iso_asset(asset)


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


# ── 项目 CRUD + 时间轴 ────────────────────────────────────


def iso_project(project: dict[str, object]) -> dict[str, object]:
    out = dict(project)
    for key in ("created_at", "updated_at"):
        ts = out.get(key)
        if isinstance(ts, (int, float)):
            from datetime import datetime, timezone
            out[key] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return out


async def _sync_asset_refs(old_ids: list[str], new_ids: list[str]) -> None:
    """引用计数同步：移除的减一、新增的加一。"""
    old_set, new_set = set(old_ids), set(new_ids)
    for aid in old_set - new_set:
        await composer_store.decr_ref(aid)
    for aid in new_set - old_set:
        await composer_store.incr_ref(aid)


class ProjectCreateRequest(BaseModel):
    title: str | None = Field(default=None, description="项目标题")
    script: str | None = Field(default=None, description="脚本文本")


class ProjectUpdateRequest(BaseModel):
    title: str | None = Field(default=None, description="项目标题")
    script: str | None = Field(default=None, description="脚本文本")
    timeline: dict[str, object] | None = Field(default=None, description="完整时间轴（走 Schema 校验）")


@router.get("/projects")
async def list_projects():
    """项目列表（含完整时间轴，按更新时间倒序）。"""
    projects = await composer_store.list_projects()
    return {"projects": [iso_project(p) for p in projects]}


@router.post("/projects")
async def create_project(req: ProjectCreateRequest):
    """创建项目（可携带脚本），时间轴初始化为空骨架。"""
    from composer.timeline import empty_timeline
    from llm.constants import COMPOSER_PRESET_DEFAULT, PROJECT_DEFAULT_TITLE

    preset = COMPOSER_PRESET_DEFAULT
    project = await composer_store.create_project(
        title=req.title or PROJECT_DEFAULT_TITLE,
        script=req.script or "",
        timeline=empty_timeline(preset),
        asset_ids=[],
    )
    await broadcast_project("created", iso_project(project))
    return iso_project(project)


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """项目详情（含完整时间轴）。"""
    project = await composer_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return iso_project(project)


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, req: ProjectUpdateRequest):
    """更新标题 / 脚本 / 时间轴。时间轴先走 Schema 校验，失败返回逐字段错误。"""
    existing = await composer_store.get_project(project_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    new_asset_ids: list[str] | None = None
    if req.timeline is not None:
        assets = await composer_store.list_assets()
        errors = composer_timeline.validate_timeline(
            req.timeline, assets, composer_config.get_presets()
        )
        if errors:
            raise HTTPException(status_code=400, detail={"message": "时间轴校验失败", "errors": errors})
        new_asset_ids = composer_timeline.timeline_asset_ids(req.timeline)

    raw_old = existing.get("asset_ids")
    old_ids = [str(x) for x in raw_old] if isinstance(raw_old, list) else []
    project = await composer_store.update_project(
        project_id,
        title=req.title,
        script=req.script,
        timeline=req.timeline,
        asset_ids=new_asset_ids,
    )
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if new_asset_ids is not None:
        await _sync_asset_refs(old_ids, new_asset_ids)
    await broadcast_project("updated", iso_project(project))
    return iso_project(project)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """删除项目（引用计数递减，素材归零后可再删）。"""
    existing = await composer_store.get_project(project_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    raw_old = existing.get("asset_ids")
    old_ids = [str(x) for x in raw_old] if isinstance(raw_old, list) else []
    await _sync_asset_refs(old_ids, [])
    deleted = await composer_store.delete_project(project_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    await broadcast_project("deleted", {"project_id": project_id})
    return {"ok": True, "deleted": project_id}


@router.get("/projects/{project_id}/srt")
async def get_project_srt(project_id: str):
    """下载项目当前时间轴的字幕 SRT。"""
    project = await composer_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    timeline = project.get("timeline") if isinstance(project.get("timeline"), dict) else {}
    tracks = (timeline or {}).get("tracks") if isinstance(timeline, dict) else {}
    subs = (tracks or {}).get("subtitles") if isinstance(tracks, dict) else []
    srt = composer_timeline.generate_srt(subs if isinstance(subs, list) else [])
    return Response(
        content=srt,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{project_id}.srt"'},
    )


# ── 渲染任务（M3）─────────────────────────────────────────


@router.post("/projects/{project_id}/render")
async def start_render(project_id: str):
    """提交项目渲染（校验时间轴 → 入队），返回 render_id。"""
    try:
        render = await render_queue.submit(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from None
    return _merged_render(render)


@router.get("/renders")
async def list_renders(project_id: str | None = None):
    """渲染任务列表（按创建时间倒序，可 project_id 过滤）。"""
    renders = await composer_store.list_renders(project_id)
    return {"renders": [_merged_render(r) for r in renders]}


@router.get("/renders/{render_id}")
async def get_render(render_id: str):
    """渲染任务详情（含实时进度）。"""
    render = await composer_store.get_render(render_id)
    if render is None:
        raise HTTPException(status_code=404, detail=MSG_RENDER_NOT_FOUND)
    return _merged_render(render)


@router.post("/renders/{render_id}/cancel")
async def cancel_render(render_id: str):
    """取消渲染（queued 直接置 canceled；运行中杀 ffmpeg 子进程）。"""
    render = await render_queue.cancel(render_id)
    if render is None:
        raise HTTPException(status_code=404, detail=MSG_RENDER_NOT_FOUND)
    return _merged_render(render)


@router.get("/renders/{render_id}/file")
async def stream_render_file(render_id: str, request: Request, download: int = 0):
    """成品 MP4 流式播放（Range）/ `?download=1` 附件下载。"""
    render = await composer_store.get_render(render_id)
    if render is None:
        raise HTTPException(status_code=404, detail=MSG_RENDER_NOT_FOUND)
    if str(render["state"]) != RENDER_COMPLETED or not render["output_path"]:
        raise HTTPException(status_code=409, detail="渲染尚未完成")
    path = composer_assets.asset_abs_path(str(render["output_path"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="渲染产物文件缺失")
    return _stream_file_response(
        path, "video/mp4", request, download_name=f"{render_id}.mp4" if download else None
    )


# ── 素材文件流（Range 支持，供预览播放）────────────────────

_RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


def _content_type_for(asset: dict[str, object]) -> str:
    ext = Path(str(asset.get("file_path", ""))).suffix.lower()
    entry = COMPOSER_MEDIA_EXTS.get(ext)
    if entry:
        return entry[1]
    kind = asset.get("kind")
    return {COMPOSER_KIND_IMAGE: "image/png", COMPOSER_KIND_VIDEO: "video/mp4", COMPOSER_KIND_AUDIO: "audio/mpeg"}.get(str(kind), "application/octet-stream")


def _stream_file_response(
    path: Path, content_type: str, request: Request, download_name: str | None = None
):
    """通用文件流式响应（HTTP Range + 可选附件下载）。"""
    size = path.stat().st_size
    range_header = request.headers.get("range")
    extra: dict[str, str] = {}
    if download_name:
        extra["Content-Disposition"] = f'attachment; filename="{download_name}"'

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
            **extra,
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
        **extra,
    }
    return StreamingResponse(_chunk_stream(start, end), status_code=206, headers=headers)


@router.get("/assets/{asset_id}/file")
async def stream_asset_file(asset_id: str, request: Request):
    """素材流式播放（支持 HTTP Range，供视频预览 / 音频试听）。"""
    asset = await composer_store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    path = composer_assets.asset_abs_path(str(asset["file_path"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="素材文件缺失")
    return _stream_file_response(path, _content_type_for(asset), request)


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


async def _config_response() -> dict[str, object]:
    return {
        "config": composer_config.snapshot(),
        **composer_ffmpeg.availability_snapshot(),
        "providers": {
            "tts": await composer_tts.probe(),
            "music": await composer_music.probe(),
        },
    }


@router.get("/config")
async def get_config():
    """合成器配置 + ffmpeg / TTS / 音乐 provider 探测结果。"""
    return await _config_response()


@router.put("/config")
async def put_config(updates: dict[str, object]):
    """更新合成器配置（ffmpeg 路径变更后立即重新探测）。"""
    snapshot = composer_config.apply(updates)
    await composer_ffmpeg.refresh_availability(str(snapshot.get("ffmpeg_path", "")))
    return await _config_response()
