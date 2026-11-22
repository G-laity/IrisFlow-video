"""ffmpeg / ffprobe 探测与调用。

M1：二进制定位（配置路径 → PATH）+ 可用性探测 + ffprobe 媒体元数据。
M3：扩展命令构建、分段渲染、进度解析与子进程管理。
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path

from llm.constants import COMPOSER_PROBE_TIMEOUT

_log = logging.getLogger(__name__)

# ffprobe 将图片也报告为 codec_type=video 的流，需按 codec 名识别为静态图
IMAGE_CODECS = {"png", "mjpeg", "gif", "bmp", "webp", "tiff", "jpeg2000", "dpx", "targa"}

# ── 运行期状态 ────────────────────────────────────────────

ffmpeg_path: str = ""
ffprobe_path: str = ""
ffmpeg_available: bool = False
ffprobe_available: bool = False
last_probe_error: str = ""


def _exe(name: str) -> str:
    """Windows 下追加 .exe 后缀。"""
    return name + (".exe" if sys.platform == "win32" else "")


def _resolve(name: str, custom_dir: str = "") -> str | None:
    """按序定位可执行文件：自定义路径 → PATH。"""
    if custom_dir:
        p = Path(custom_dir)
        candidate = p if p.is_file() else p / _exe(name)
        if candidate.is_file():
            return str(candidate.resolve())
    found = shutil.which(_exe(name))
    return str(found) if found else None


async def refresh_availability(custom_path: str = "") -> None:
    """重新探测 ffmpeg / ffprobe 并更新模块级状态。

    探测失败不抛异常：记录错误原因，状态置 False（与 MCP 初始化一致）。
    """
    global ffmpeg_path, ffprobe_path, ffmpeg_available, ffprobe_available, last_probe_error
    ffmpeg_path = _resolve("ffmpeg", custom_path) or ""
    ffprobe_path = _resolve("ffprobe", custom_path) or ""
    ffmpeg_available = bool(ffmpeg_path)
    ffprobe_available = bool(ffprobe_path)
    if ffmpeg_available and ffprobe_available:
        last_probe_error = ""
        _log.info("ffmpeg 可用: %s | ffprobe 可用: %s", ffmpeg_path, ffprobe_path)
        return

    missing: list[str] = []
    if not ffmpeg_available:
        missing.append("ffmpeg")
    if not ffprobe_available:
        missing.append("ffprobe")
    last_probe_error = (
        f"未找到 {'、'.join(missing)}。请安装 ffmpeg（https://ffmpeg.org/download.html）"
        "或在合成器设置中配置自定义路径。"
    )
    _log.warning("ffmpeg 探测失败: %s", last_probe_error)


async def probe_media(file_path: str) -> dict[str, object]:
    """ffprobe 探测媒体元数据。

    Returns:
        统一结构 probe 字典（与素材记录的 probe 字段一致）。
        视频: duration/width/height/fps/vcodec/acodec/has_audio
        图片: width/height（无 duration）
        音频: duration/acodec

    Raises:
        RuntimeError: ffprobe 不可用或探测失败（错误信息含 stderr 尾部）。
    """
    if not ffprobe_available or not ffprobe_path:
        await refresh_availability()
        if not ffprobe_available:
            raise RuntimeError(last_probe_error or "ffprobe 不可用")

    cmd = [
        ffprobe_path,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=COMPOSER_PROBE_TIMEOUT
        )
    except asyncio.TimeoutError:
        raise RuntimeError("ffprobe 探测超时") from None
    except OSError as e:
        raise RuntimeError(f"ffprobe 启动失败: {e}") from None

    if proc.returncode != 0:
        tail = stderr.decode("utf-8", errors="replace").strip()[-300:]
        raise RuntimeError(f"ffprobe 探测失败: {tail or '未知错误'}")

    try:
        data = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        raise RuntimeError("ffprobe 输出解析失败") from None

    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    probe: dict[str, object] = {}

    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    # 图片：ffprobe 报 codec_type=video 但 codec 为静态图编码 → 仅取宽高
    if video is not None and str(video.get("codec_name") or "").lower() in IMAGE_CODECS:
        probe["width"] = int(video.get("width", 0) or 0)
        probe["height"] = int(video.get("height", 0) or 0)
        return probe

    # 时长：优先 video stream 时长，其次 format 时长
    duration: float | None = None
    raw_dur = (video or {}).get("duration") or fmt.get("duration")
    if raw_dur is not None:
        try:
            duration = float(raw_dur)
        except (TypeError, ValueError):
            duration = None
    if duration is not None:
        probe["duration"] = round(duration, 3)

    if video is not None:
        probe["width"] = int(video.get("width", 0) or 0)
        probe["height"] = int(video.get("height", 0) or 0)
        probe["vcodec"] = str(video.get("codec_name") or "")
        # fps：解析 avg_frame_rate "30000/1001" 形式
        fps_raw = str(video.get("avg_frame_rate") or "")
        if "/" in fps_raw:
            try:
                num, den = fps_raw.split("/", 1)
                den_f = float(den)
                probe["fps"] = round(float(num) / den_f, 3) if den_f else 0.0
            except (ValueError, ZeroDivisionError):
                pass
    if audio is not None:
        probe["acodec"] = str(audio.get("codec_name") or "")
    probe["has_audio"] = audio is not None

    return probe


def availability_snapshot() -> dict[str, object]:
    """返回探测结果快照（GET /api/composer/config 用）。"""
    return {
        "ffmpeg_available": ffmpeg_available,
        "ffprobe_available": ffprobe_available,
        "ffmpeg_path": ffmpeg_path,
        "ffprobe_path": ffprobe_path,
        "error": last_probe_error,
    }
