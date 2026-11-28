"""视频合成器内置工具集（M2：编排 + 语音/音乐生成；渲染 M3）。

工具高合并度设计：一次调用完成「生成 + 入库」「校验 + 写入时间轴」，
对抗 Agent 迭代轮次上限（PLAN §8.3）。
"""

from __future__ import annotations

import asyncio
import json
import logging

# 注意：composer.* 必须懒加载（在 execute 内导入）。
# 顶层导入会形成循环：composer.ffmpeg → llm.constants → llm/__init__
# → llm.router → llm.tools → 本模块 → composer.assets → composer.ffmpeg。
from llm.constants import (
    AGNES_VIDEO_POLL_INTERVAL,
    AGNES_VIDEO_POLL_MAX,
    MSG_COMPOSER_GROUP,
    MSG_MUSIC_UNAVAILABLE,
    RENDER_COMPLETED,
)
from llm.models import ToolDefinition
from llm.tools.base import Tool

_log = logging.getLogger(__name__)

_GROUP = MSG_COMPOSER_GROUP

_TIMELINE_TEMPLATE = """{
  "version": 1,
  "preset": "720p16x9",
  "tracks": {
    "video": [
      {
        "asset_id": "as_...",
        "duration": 5.0,
        "trim_in": 0.0,
        "transition_in": {"type": "fade", "duration": 0.5},
        "motion": {"type": "kenburns", "from_zoom": 1.0, "to_zoom": 1.15, "pan": "none"}
      }
    ],
    "audio": [
      {
        "role": "narration",
        "asset_id": "as_...",
        "start": 0.0,
        "duration": 10.0,
        "gain": 1.0,
        "fade_in": 0.0,
        "fade_out": 0.0,
        "loop": false
      },
      {
        "role": "bgm",
        "asset_id": "as_...",
        "start": 0.0,
        "duration": 15.0,
        "gain": 0.35,
        "fade_in": 0.5,
        "fade_out": 2.0,
        "loop": true
      }
    ],
    "subtitles": [
      {"start": 0.2, "end": 3.5, "text": "第一句旁白", "style": "default"}
    ]
  }
}"""


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


async def _require_project(project_id: str) -> dict[str, object]:
    from composer.store import composer_store

    project = await composer_store.get_project(project_id)
    if project is None:
        raise RuntimeError(f"项目不存在: {project_id}")
    return project


async def _broadcast_asset(asset: dict[str, object]) -> None:
    """延迟导入避免工具模块与路由模块的初始化顺序耦合。"""
    from composer.router import iso_asset, broadcast_asset
    await broadcast_asset("created", iso_asset(asset))


async def _broadcast_project(event: str, project: dict[str, object]) -> None:
    from composer.router import iso_project, broadcast_project
    await broadcast_project(event, iso_project(project))


# ── 项目 ──────────────────────────────────────────────────


class ComposerCreateProjectTool(Tool):
    definition = ToolDefinition(
        name="composer_create_project",
        description=(
            "创建一个视频合成项目。返回 project_id，后续素材编排与时间轴写入都使用该 ID。"
            "script 可传入完整分镜脚本，作为后续编排依据。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "项目标题"},
                "script": {"type": "string", "description": "分镜脚本文本（可选）"},
            },
            "required": ["title"],
        },
    )
    icon = "fa-solid fa-clapperboard"
    label = "创建合成项目"
    order = 10.0
    group = _GROUP

    async def execute(self, **kwargs: object) -> str:
        from composer import timeline as composer_timeline
        from composer.store import composer_store
        from llm.constants import COMPOSER_PRESET_DEFAULT, PROJECT_DEFAULT_TITLE

        title = str(kwargs.get("title") or PROJECT_DEFAULT_TITLE)
        script = str(kwargs.get("script") or "")
        project = await composer_store.create_project(
            title=title,
            script=script,
            timeline=composer_timeline.empty_timeline(COMPOSER_PRESET_DEFAULT),
            asset_ids=[],
        )
        _log.info("工具创建项目: %s", project["project_id"])
        await _broadcast_project("created", project)
        return _json({"project_id": project["project_id"], "title": title, "preset": COMPOSER_PRESET_DEFAULT})


# ── 素材导入 ──────────────────────────────────────────────


class ComposerImportAssetTool(Tool):
    definition = ToolDefinition(
        name="composer_import_asset",
        description=(
            "从 URL 下载素材（图片 / 视频 / 音频）并入库，自动去重与探测元数据。"
            "返回 asset_id 与宽度/高度/时长/编码等摘要。同一 URL 重复导入会复用已有素材。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "素材 URL（http/https）"},
                "kind": {
                    "type": "string",
                    "description": "类型提示：image / video / audio（可省略，以探测为准）",
                },
            },
            "required": ["url"],
        },
    )
    icon = "fa-solid fa-download"
    label = "导入素材 URL"
    order = 11.0
    group = _GROUP

    async def execute(self, **kwargs: object) -> str:
        from composer import assets as composer_assets

        url = str(kwargs.get("url") or "").strip()
        if not url:
            raise RuntimeError("缺失 url")
        kind = kwargs.get("kind")
        asset, duplicated = await composer_assets.import_from_url(
            url, str(kind) if kind else None
        )
        if not duplicated:
            await _broadcast_asset(asset)
        return _json({
            "asset_id": asset["asset_id"],
            "kind": asset["kind"],
            "duplicated": duplicated,
            "probe": asset["probe"],
            "size_bytes": asset["size_bytes"],
        })


class ComposerImportGeneratedTool(Tool):
    definition = ToolDefinition(
        name="composer_import_generated",
        description=(
            "Agnes 专用：传入 agnes_video_create 返回的 video_id，工具自动轮询视频生成状态"
            "（最长 10 分钟），完成后立即下载入库（Agnes URL 会过期）。"
            "返回 asset_id 与探测元数据；无需再手动调 agnes_video_status。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "video_id": {"type": "string", "description": "agnes_video_create 返回的 video_id"},
            },
            "required": ["video_id"],
        },
    )
    icon = "fa-solid fa-wand-magic-sparkles"
    label = "导入 Agnes 视频"
    order = 12.0
    group = _GROUP

    async def execute(self, **kwargs: object) -> str:
        from composer import assets as composer_assets
        from llm.tools import tool_executor

        video_id = str(kwargs.get("video_id") or "").strip()
        if not video_id:
            raise RuntimeError("缺失 video_id")
        if not tool_executor.can_execute("agnes_video_status"):
            raise RuntimeError("Agnes MCP 服务未注册（缺少 agnes_video_status），请先在 mcp.json 配置 agnes")

        waited = 0.0
        last_status = "unknown"
        url = ""
        while waited <= AGNES_VIDEO_POLL_MAX:
            text, is_error = await tool_executor.execute(
                "agnes_video_status", {"video_id": video_id}
            )
            if is_error:
                raise RuntimeError(f"查询 Agnes 状态失败: {text}")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                raise RuntimeError(f"Agnes 状态返回非 JSON: {text[:300]}") from None
            last_status = str(payload.get("status") or payload.get("state") or "unknown").lower()
            url = _find_url(payload)
            if url and last_status in ("completed", "succeeded", "success", "done", "finished"):
                break
            if last_status in ("failed", "error", "cancelled"):
                raise RuntimeError(f"Agnes 视频生成失败: {text[:500]}")
            await asyncio.sleep(AGNES_VIDEO_POLL_INTERVAL)
            waited += AGNES_VIDEO_POLL_INTERVAL

        if not url:
            raise RuntimeError(
                f"等待 Agnes 视频超时（{int(AGNES_VIDEO_POLL_MAX)}s），最后状态: {last_status}"
            )
        asset, duplicated = await composer_assets.import_from_url(url, "video")
        if not duplicated:
            await _broadcast_asset(asset)
        return _json({
            "asset_id": asset["asset_id"],
            "kind": asset["kind"],
            "duplicated": duplicated,
            "probe": asset["probe"],
            "agnes_video_id": video_id,
        })


def _find_url(obj: object) -> str:
    """递归查找首个 http(s) URL 字段（优先 url / video_url / output_url）。"""
    preferred = ("video_url", "output_url", "url")
    if isinstance(obj, dict):
        for key in preferred:
            val = obj.get(key)
            if isinstance(val, str) and val.startswith("http"):
                return val
        for val in obj.values():
            found = _find_url(val)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_url(item)
            if found:
                return found
    return ""


# ── 语音 / 音乐生成 ───────────────────────────────────────


class ComposerTtsTool(Tool):
    definition = ToolDefinition(
        name="composer_tts",
        description=(
            "将文本合成为旁白语音并自动入库（source=tts），一次调用完成合成 + 入库。"
            "返回 asset_id 与探测时长（秒）——请用该时长对齐镜头时长与字幕节奏。"
            "长文本（>80 字）默认自动分句合成后拼接；多说话人对话用 segments 传入"
            "（JSON 数组 [{\"text\": \"...\", \"voice\": \"旁白·女\"}]，与 text 二选一）。"
            "voice 使用配置中的命名音色（默认「旁白·男」）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "旁白文本（与 segments 二选一）"},
                "segments": {
                    "type": "string",
                    "description": "多说话人片段 JSON 数组，如 [{\"text\":\"你好\",\"voice\":\"旁白·女\"}]",
                },
                "voice": {"type": "string", "description": "命名音色，如「旁白·男」「旁白·女」"},
                "speed": {"type": "number", "description": "语速倍率，默认 1.0"},
                "split": {"type": "boolean", "description": "长文本是否自动分句（默认 true）"},
            },
            "required": [],
        },
    )
    icon = "fa-solid fa-microphone"
    label = "合成旁白"
    order = 13.0
    group = _GROUP

    async def execute(self, **kwargs: object) -> str:
        from composer import assets as composer_assets
        from composer import tts as composer_tts

        text = str(kwargs.get("text") or "").strip()
        raw_segments = kwargs.get("segments")
        segments: list[dict[str, object]] | None = None
        if raw_segments:
            if isinstance(raw_segments, str):
                try:
                    parsed = json.loads(raw_segments)
                except json.JSONDecodeError as e:
                    return f"segments JSON 解析失败: {e}"
            else:
                parsed = raw_segments
            if isinstance(parsed, list):
                segments = [s for s in parsed if isinstance(s, dict)]
        if not text and not segments:
            raise RuntimeError("缺失 text 或 segments")
        voice = kwargs.get("voice")
        speed = kwargs.get("speed")
        split = kwargs.get("split", True)
        if segments:
            data, ext, provider = await composer_tts.synthesize_dialogue(
                segments, float(speed) if isinstance(speed, (int, float)) else None
            )
            meta_text = f"[dialogue:{len(segments)}]"
        else:
            data, ext, provider = await composer_tts.synthesize(
                text,
                str(voice) if voice else None,
                float(speed) if isinstance(speed, (int, float)) else None,
                split=bool(split),
            )
            meta_text = text[:200]
        asset, duplicated = await composer_assets.import_from_bytes(
            data, f".{ext}", "tts",
            meta={"model": provider, "voice": str(voice or ""), "text": meta_text},
        )
        if not duplicated:
            await _broadcast_asset(asset)
        raw_probe = asset.get("probe")
        probe: dict[str, object] = raw_probe if isinstance(raw_probe, dict) else {}
        return _json({
            "asset_id": asset["asset_id"],
            "provider": provider,
            "duration": probe.get("duration"),
            "duplicated": duplicated,
        })


class ComposerBgmTool(Tool):
    definition = ToolDefinition(
        name="composer_bgm",
        description=(
            "生成背景音乐片段并自动入库（source=music）。返回 asset_id 与时长。"
            "时间轴 BGM 轨设置 loop=true 可自动循环铺满全片。"
            "服务不可用时返回引导信息（改为上传或 URL 导入 BGM），不阻塞编排。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "style": {"type": "string", "description": "音乐风格 / 情绪描述，如「轻快的电子氛围」"},
                "duration": {"type": "integer", "description": "片段时长（秒），默认 11"},
                "mood": {"type": "string", "description": "情绪补充描述（可选，拼入 prompt）"},
            },
            "required": ["style"],
        },
    )
    icon = "fa-solid fa-music"
    label = "生成背景音乐"
    order = 14.0
    group = _GROUP

    async def execute(self, **kwargs: object) -> str:
        from composer import assets as composer_assets
        from composer import music as composer_music

        style = str(kwargs.get("style") or "").strip()
        if not style:
            raise RuntimeError("缺失 style")
        mood = str(kwargs.get("mood") or "").strip()
        prompt = f"{style}，{mood}" if mood else style
        duration = kwargs.get("duration")
        try:
            data, ext = await composer_music.generate(
                prompt, int(duration) if isinstance(duration, (int, float)) else None  # type: ignore[arg-type]
            )
        except RuntimeError as e:
            return _json({
                "ok": False,
                "guidance": MSG_MUSIC_UNAVAILABLE,
                "detail": str(e),
                "suggestion": "请改用 composer_import_asset 导入现成 BGM，或让用户上传音频素材。",
            })
        asset, duplicated = await composer_assets.import_from_bytes(
            data, f".{ext}", "music", meta={"prompt": prompt}
        )
        if not duplicated:
            await _broadcast_asset(asset)
        raw_probe = asset.get("probe")
        probe: dict[str, object] = raw_probe if isinstance(raw_probe, dict) else {}
        return _json({
            "ok": True,
            "asset_id": asset["asset_id"],
            "duration": probe.get("duration"),
            "duplicated": duplicated,
        })


# ── 时间轴 / 渲染 ─────────────────────────────────────────


class ComposerSetTimelineTool(Tool):
    definition = ToolDefinition(
        name="composer_set_timeline",
        description=(
            "校验并整体写入项目时间轴（一次调用写全量，高合并度）。"
            "timeline 参数为 JSON 字符串，结构模板：\n"
            + _TIMELINE_TEMPLATE
            + "\n约束：video 轨 asset 必须为 video/image；视频段 duration ≤ 素材时长；"
            "图片段 duration ∈ [0.5, 30]；audio 轨 role 为 narration/bgm、asset 必须为 audio；"
            "subtitles 需 start < end 且 text 非空；transition duration 必须小于相邻两段时长。"
            "校验失败会返回逐字段错误，修正后重试。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目 ID"},
                "timeline": {"type": "string", "description": "完整时间轴 JSON 字符串"},
            },
            "required": ["project_id", "timeline"],
        },
    )
    icon = "fa-solid fa-bars-staggered"
    label = "写入时间轴"
    order = 15.0
    group = _GROUP

    async def execute(self, **kwargs: object) -> str:
        from composer import config as composer_config
        from composer import timeline as composer_timeline
        from composer.store import composer_store

        project_id = str(kwargs.get("project_id") or "")
        raw = kwargs.get("timeline")
        if isinstance(raw, dict):
            timeline_obj: object = raw
        else:
            try:
                timeline_obj = json.loads(str(raw or ""))
            except json.JSONDecodeError as e:
                return f"timeline JSON 解析失败: {e}"
        project = await _require_project(project_id)
        assets = await composer_store.list_assets()
        errors = composer_timeline.validate_timeline(
            timeline_obj, assets, composer_config.get_presets()
        )
        if errors:
            return "时间轴校验失败：\n- " + "\n- ".join(errors)

        timeline_dict: dict[str, object] = timeline_obj if isinstance(timeline_obj, dict) else {}
        new_ids = composer_timeline.timeline_asset_ids(timeline_dict)
        raw_old = project.get("asset_ids")
        old_ids = [str(x) for x in raw_old] if isinstance(raw_old, list) else []
        updated = await composer_store.update_project(
            project_id, timeline=timeline_dict, asset_ids=new_ids
        )
        for aid in set(old_ids) - set(new_ids):
            await composer_store.decr_ref(aid)
        for aid in set(new_ids) - set(old_ids):
            await composer_store.incr_ref(aid)
        assert updated is not None
        await _broadcast_project("updated", updated)
        raw_tracks = timeline_dict.get("tracks")
        tracks: dict[str, object] = raw_tracks if isinstance(raw_tracks, dict) else {}

        def _count(key: str) -> int:
            value = tracks.get(key)
            return len(value) if isinstance(value, list) else 0

        _log.info("工具写入时间轴: %s", project_id)
        return _json({
            "ok": True,
            "project_id": project_id,
            "segments": _count("video"),
            "audio_tracks": _count("audio"),
            "subtitles": _count("subtitles"),
        })


class ComposerStartRenderTool(Tool):
    definition = ToolDefinition(
        name="composer_start_render",
        description=(
            "提交项目渲染任务（异步队列）。返回 render_id 后不要阻塞等待，"
            "告知用户可在合成器「渲染」标签页查看进度；稍后可调 composer_render_status 查询。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目 ID"},
            },
            "required": ["project_id"],
        },
    )
    icon = "fa-solid fa-film"
    label = "提交渲染"
    order = 16.0
    group = _GROUP

    async def execute(self, **kwargs: object) -> str:
        from composer.queue import render_queue

        project_id = str(kwargs.get("project_id") or "")
        await _require_project(project_id)
        try:
            render = await render_queue.submit(project_id)
        except ValueError as e:
            return _json({"ok": False, "message": str(e), "project_id": project_id})
        except RuntimeError as e:
            return _json({"ok": False, "message": str(e), "project_id": project_id})
        return _json({
            "ok": True,
            "render_id": render["render_id"],
            "state": render["state"],
            "hint": "渲染在后台进行，可在合成器「渲染」标签页查看进度与成品。",
        })


class ComposerListVideosTool(Tool):
    definition = ToolDefinition(
        name="composer_list_videos",
        description=(
            "列出本机合成器中的素材和已完成渲染成片。"
            "用户询问「有哪些视频 / 素材 / 图片 / 音频 / 成品视频」时优先调用；"
            "不要用 web_search 查询本机内容。kind 默认 all（图片 + 视频 + 音频），"
            "只问视频时传 video，只问图片/音频时传 image/audio。"
            "返回 asset_id / kind / 文件名 / 时长 / file_url / render_id / download_url 等。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["all", "video", "image", "audio"],
                    "description": "素材类型，默认 all；成片只在 all/video 时返回",
                },
                "limit": {
                    "type": "integer",
                    "description": "每类最多返回多少条（默认 20，最大 50）",
                },
            },
            "required": [],
        },
    )
    icon = "fa-solid fa-photo-film"
    label = "列出素材"
    order = 9.0
    group = _GROUP

    async def execute(self, **kwargs: object) -> str:
        from composer.store import composer_store

        limit = max(1, min(50, int(_to_float(kwargs.get("limit"), 20))))
        kind = str(kwargs.get("kind") or "all").lower()
        if kind not in ("all", "video", "image", "audio"):
            kind = "all"
        include_renders = kind in ("all", "video")

        assets = await composer_store.list_assets(None if kind == "all" else kind)
        projects = await composer_store.list_projects()
        titles = {str(p["project_id"]): str(p.get("title") or "") for p in projects}

        media_assets: list[dict[str, object]] = []
        for asset in assets[:limit]:
            asset_id = str(asset["asset_id"])
            probe = asset.get("probe")
            duration = None
            if isinstance(probe, dict) and probe.get("duration") is not None:
                duration = round(_to_float(probe.get("duration")), 3)
            media_assets.append({
                "asset_id": asset_id,
                "kind": str(asset.get("kind") or ""),
                "name": _asset_name(asset),
                "duration": duration,
                "size_bytes": asset.get("size_bytes"),
                "source": asset.get("source"),
                "created_at": asset.get("created_at"),
                "file_url": f"/api/composer/assets/{asset_id}/file",
            })

        completed: list[dict[str, object]] = []
        if include_renders:
            renders = await composer_store.list_renders()
            completed = [
                r for r in renders
                if str(r.get("state")) == RENDER_COMPLETED and r.get("output_path")
            ]
        render_items: list[dict[str, object]] = []
        for render in completed[:limit]:
            render_id = str(render["render_id"])
            base = f"/api/composer/renders/{render_id}/file"
            render_items.append({
                "render_id": render_id,
                "project_id": render.get("project_id"),
                "project_title": titles.get(str(render.get("project_id") or ""), ""),
                "state": render.get("state"),
                "finished_at": render.get("finished_at"),
                "file_url": base,
                "download_url": f"{base}?download=1",
            })

        result: dict[str, object] = {
            "kind": kind,
            "assets": media_assets,
            "renders": render_items,
            "total_assets": len(assets),
            "total_renders": len(completed),
            "limit": limit,
        }
        if not media_assets and not render_items:
            result["hint"] = "本机合成器没有匹配的素材或已完成成片。"
        else:
            result["hint"] = (
                "assets 是素材库中的图片/视频/音频（看 kind 字段），renders 是已完成成片；"
                "file_url 可播放，download_url 可下载。"
            )
        return _json(result)


def _asset_name(asset: dict[str, object]) -> str:
    """尽力取素材的可读文件名（meta → URL basename → 本地 basename）。"""
    meta = asset.get("meta")
    if isinstance(meta, dict):
        for key in ("filename", "name", "original_name"):
            value = meta.get(key)
            if value:
                return str(value)
    url = str(asset.get("url") or "")
    if url:
        name = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        if name:
            return name
    file_path = str(asset.get("file_path") or "")
    return file_path.rsplit("/", 1)[-1] if file_path else str(asset.get("asset_id") or "")


class ComposerRenderStatusTool(Tool):
    definition = ToolDefinition(
        name="composer_render_status",
        description=(
            "查询渲染任务状态与进度（渲染中调用不阻塞）；"
            "完成时返回 file_url / download_url，可直接作为成品视频播放/下载地址。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "render_id": {"type": "string", "description": "渲染任务 ID"},
            },
            "required": ["render_id"],
        },
    )
    icon = "fa-solid fa-circle-info"
    label = "渲染状态"
    order = 17.0
    group = _GROUP

    async def execute(self, **kwargs: object) -> str:
        from composer.queue import render_queue
        from composer.store import composer_store

        render_id = str(kwargs.get("render_id") or "")
        render = await composer_store.get_render(render_id)
        if render is None:
            return _json({"ok": False, "message": "渲染任务不存在", "render_id": render_id})
        live = render_queue.live_snapshot(render_id)
        if live:
            render.update(live)
        output_ready = render["state"] == RENDER_COMPLETED and bool(render.get("output_path"))
        result: dict[str, object] = {
            "render_id": render_id,
            "project_id": render["project_id"],
            "state": render["state"],
            "progress": round(_to_float(render.get("progress")), 3),
            "stage_detail": render.get("stage_detail") or {},
            "error": render.get("error") or "",
            "output_ready": output_ready,
        }
        if output_ready:
            base = f"/api/composer/renders/{render_id}/file"
            result["file_url"] = base
            result["download_url"] = f"{base}?download=1"
        return _json(result)


COMPOSER_TOOLS: list[Tool] = [
    ComposerListVideosTool(),
    ComposerCreateProjectTool(),
    ComposerImportAssetTool(),
    ComposerImportGeneratedTool(),
    ComposerTtsTool(),
    ComposerBgmTool(),
    ComposerSetTimelineTool(),
    ComposerStartRenderTool(),
    ComposerRenderStatusTool(),
]
