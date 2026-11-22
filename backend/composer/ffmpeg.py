"""ffmpeg / ffprobe 探测与调用。

M1：二进制定位（配置路径 → PATH）+ 可用性探测 + ffprobe 媒体元数据。
M3：扩展命令构建、分段渲染、进度解析与子进程管理。
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from composer import config as composer_config
from llm.constants import (
    COMPOSER_PROBE_TIMEOUT,
    FFMPEG_AUDIO_BITRATE,
    FFMPEG_AUDIO_SAMPLE_RATE,
    FFMPEG_CRF,
    FFMPEG_PIX_FMT,
    FFMPEG_VIDEO_PRESET,
    RENDER_ERROR_TAIL,
    SIDECHAIN_ATTACK,
    SIDECHAIN_RATIO,
    SIDECHAIN_RELEASE,
    SIDECHAIN_THRESHOLD,
    XFADE_TYPE_MAP,
)

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

    def _run() -> tuple[int, bytes, bytes]:
        # 用 subprocess.run + 线程，兼容 Windows SelectorEventLoop
        completed = subprocess.run(
            cmd, capture_output=True, timeout=COMPOSER_PROBE_TIMEOUT, check=False
        )
        return completed.returncode, completed.stdout, completed.stderr

    try:
        returncode, stdout, stderr = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffprobe 探测超时") from None
    except OSError as e:
        raise RuntimeError(f"ffprobe 启动失败: {e}") from None

    if returncode != 0:
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


# ── 渲染命令构建（M3）─────────────────────────────────────


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _encoding() -> tuple[str, str, str]:
    """返回 (preset, crf, audio_bitrate)，配置缺失时回退常量。"""
    enc = composer_config.get_encoding()
    preset = str(enc.get("preset") or FFMPEG_VIDEO_PRESET)
    crf = str(enc.get("crf") if enc.get("crf") is not None else FFMPEG_CRF)
    audio_bitrate = str(enc.get("audio_bitrate") or FFMPEG_AUDIO_BITRATE)
    return preset, crf, audio_bitrate


def _vf_normalize(width: int, height: int, fps: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,fps={fps},format={FFMPEG_PIX_FMT}"
    )


def _kenburns_vf(motion: dict[str, object], width: int, height: int, fps: int, duration: float) -> str:
    """Ken Burns 运镜 filter（zoompan）。"""
    from_zoom = _to_float(motion.get("from_zoom"), 1.0)
    to_zoom = _to_float(motion.get("to_zoom"), 1.0)
    pan = str(motion.get("pan") or "none")
    frames = max(1, int(round(duration * fps)))
    z = f"{from_zoom:.3f}+({to_zoom:.3f}-{from_zoom:.3f})*on/{frames}"
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    if pan == "left":
        x, y = f"(iw-iw/zoom)*(1-on/{frames})", cy
    elif pan == "right":
        x, y = f"(iw-iw/zoom)*on/{frames}", cy
    elif pan == "up":
        x, y = cx, f"(ih-ih/zoom)*(1-on/{frames})"
    elif pan == "down":
        x, y = cx, f"(ih-ih/zoom)*on/{frames}"
    else:
        x, y = cx, cy
    # 先放大 2 倍保证运镜画质，再 zoompan 到目标尺寸
    pre = (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
        f"crop={width * 2}:{height * 2}"
    )
    return (
        f"{pre},zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},"
        f"setsar=1,format={FFMPEG_PIX_FMT}"
    )


def build_segment_cmd(
    asset_path: Path,
    kind: str,
    duration: float,
    trim_in: float,
    preset: dict[str, int],
    out_path: Path,
    motion: dict[str, object] | None = None,
) -> list[str]:
    """单镜头规格化转码命令（图片循环 / 视频裁切，统一分辨率帧率，去除原声）。"""
    if not ffmpeg_path:
        raise RuntimeError(last_probe_error or "ffmpeg 不可用")
    width, height, fps = preset["width"], preset["height"], preset["fps"]
    preset_name, crf, _ = _encoding()
    if kind == "image":
        args = [ffmpeg_path, "-xerror", "-y", "-loop", "1", "-i", str(asset_path)]
        if motion and str(motion.get("type") or "") == "kenburns":
            vf = _kenburns_vf(motion, width, height, fps, duration)
        else:
            vf = _vf_normalize(width, height, fps)
    else:
        args = [ffmpeg_path, "-xerror", "-y", "-ss", f"{trim_in:.3f}", "-i", str(asset_path)]
        vf = _vf_normalize(width, height, fps)
    args += [
        "-vf", vf,
        "-c:v", "libx264", "-preset", preset_name, "-crf", crf,
        "-t", f"{duration:.3f}",
        "-an",
        str(out_path),
    ]
    return args


def build_concat_cmd(list_path: Path, out_path: Path) -> list[str]:
    """concat demuxer 拼接分段（统一规格后可直接流复制）。"""
    if not ffmpeg_path:
        raise RuntimeError(last_probe_error or "ffmpeg 不可用")
    return [
        ffmpeg_path, "-xerror", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_path), "-c", "copy", str(out_path),
    ]


def build_xfade_cmd(
    prev_path: Path,
    next_path: Path,
    transition_type: str,
    duration: float,
    offset: float,
    out_path: Path,
) -> list[str]:
    """两两 xfade 转场（输入已统一规格）。"""
    if not ffmpeg_path:
        raise RuntimeError(last_probe_error or "ffmpeg 不可用")
    preset_name, crf, _ = _encoding()
    xfade = XFADE_TYPE_MAP.get(transition_type, "fade")
    return [
        ffmpeg_path, "-xerror", "-y",
        "-i", str(prev_path), "-i", str(next_path),
        "-filter_complex",
        f"[0:v][1:v]xfade=transition={xfade}:duration={duration:.3f}:offset={offset:.3f},format={FFMPEG_PIX_FMT}[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", preset_name, "-crf", crf,
        "-an", str(out_path),
    ]


def build_mux_cmd(
    merged_path: Path,
    output_path: Path,
    subtitle_name: str | None,
    audio_tracks: list[dict[str, object]],
    total_duration: float,
) -> list[str]:
    """ASS 字幕烧录 + 音轨混合（M4：旁白侧链压 BGM）。

    Args:
        subtitle_name: ASS 文件名（相对 cwd，None = 无字幕）。
        audio_tracks: [{path, role, start, duration, gain, fade_in, fade_out, loop, ducking}]
    """
    if not ffmpeg_path:
        raise RuntimeError(last_probe_error or "ffmpeg 不可用")
    preset_name, crf, audio_bitrate = _encoding()

    args: list[str] = [ffmpeg_path, "-xerror", "-y", "-i", str(merged_path)]
    for track in audio_tracks:
        if bool(track.get("loop")):
            args += ["-stream_loop", "-1"]
        args += ["-i", str(track["path"])]

    filters: list[str] = []
    has_video_filter = False
    if subtitle_name:
        filters.append(f"[0:v]ass={subtitle_name}[vout]")
        has_video_filter = True

    all_labels: list[str] = []
    narration_labels: list[str] = []
    duck_labels: list[str] = []
    plain_labels: list[str] = []
    for i, track in enumerate(audio_tracks, start=1):
        dur = max(0.1, _to_float(track.get("duration")))
        gain = _to_float(track.get("gain"), 1.0)
        start_s = max(0.0, _to_float(track.get("start")))
        start_ms = int(round(start_s * 1000))
        fade_in = max(0.0, _to_float(track.get("fade_in")))
        fade_out = max(0.0, _to_float(track.get("fade_out")))
        chain = f"[{i}:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume={gain:.3f}"
        if fade_in > 0:
            chain += f",afade=t=in:st=0:d={fade_in:.3f}"
        if fade_out > 0:
            fo_start = max(0.0, dur - fade_out)
            chain += f",afade=t=out:st={fo_start:.3f}:d={fade_out:.3f}"
        chain += f",adelay={start_ms}|{start_ms}[a{i}]"
        filters.append(chain)
        label = f"[a{i}]"
        all_labels.append(label)
        role = str(track.get("role") or "")
        if role == "narration":
            narration_labels.append(label)
        elif role == "bgm" and bool(track.get("ducking", True)):
            duck_labels.append(label)
        else:
            plain_labels.append(label)

    final_labels: list[str] = []
    if narration_labels and duck_labels:
        filters.append(
            "".join(narration_labels)
            + f"amix=inputs={len(narration_labels)}:duration=longest:normalize=0[nar]"
        )
        filters.append("[nar]asplit=2[nar_out][nar_key]")
        filters.append(
            "".join(duck_labels)
            + f"amix=inputs={len(duck_labels)}:duration=longest:normalize=0[bgmduck_in]"
        )
        filters.append(
            f"[bgmduck_in][nar_key]sidechaincompress="
            f"threshold={SIDECHAIN_THRESHOLD}:ratio={SIDECHAIN_RATIO}:"
            f"attack={SIDECHAIN_ATTACK}:release={SIDECHAIN_RELEASE}[bgmduck]"
        )
        final_labels = ["[nar_out]", "[bgmduck]"] + plain_labels
    else:
        final_labels = all_labels

    has_audio = bool(final_labels)
    if has_audio:
        if len(final_labels) > 1:
            filters.append(
                "".join(final_labels)
                + f"amix=inputs={len(final_labels)}:duration=longest:normalize=0[amixed]"
            )
            mix_label = "[amixed]"
        else:
            mix_label = final_labels[0]
        filters.append(
            f"{mix_label}apad=whole_dur={total_duration:.3f},atrim=0:{total_duration:.3f}[aout]"
        )

    if filters:
        args += ["-filter_complex", ";".join(filters)]

    if has_video_filter:
        args += ["-map", "[vout]", "-c:v", "libx264", "-preset", preset_name, "-crf", crf]
    else:
        args += ["-map", "0:v", "-c:v", "copy"]

    if has_audio:
        args += [
            "-map", "[aout]",
            "-c:a", "aac", "-ar", str(FFMPEG_AUDIO_SAMPLE_RATE), "-b:a", audio_bitrate,
        ]
    else:
        args += ["-an"]

    args += ["-t", f"{total_duration:.3f}", "-movflags", "+faststart", str(output_path)]
    return args


# ── 子进程执行（进度解析 / 取消注册 / stderr 日志）──────────


async def run_ffmpeg(
    args: list[str],
    *,
    duration: float | None = None,
    cwd: Path | None = None,
    log_path: Path | None = None,
    on_progress: Callable[[float], None] | None = None,
    register_proc: Callable[[subprocess.Popen[str] | None], None] | None = None,
) -> None:
    """执行 ffmpeg 命令并解析 `-progress pipe:1` 输出。

    Windows 上后端可能运行在 SelectorEventLoop（asyncio 子进程不可用），
    因此统一使用 subprocess.Popen + 线程读取 stdout/stderr，兼容任意事件循环。
    Args 的最后一项必须是输出路径（本函数在输出前插入 progress 参数）。
    失败时抛 RuntimeError（含 stderr 尾部），完整 stderr 写入 log_path。
    """
    cmd = args[:-1] + ["-progress", "pipe:1", "-nostats", args[-1]]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    if register_proc:
        register_proc(proc)

    loop = asyncio.get_running_loop()
    stderr_tail: list[str] = []
    stderr_size = 0
    stderr_lock = threading.Lock()

    def _read_stdout() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            text = line.strip()
            if not text or "=" not in text:
                continue
            key, _, value = text.partition("=")
            if key in ("out_time_us", "out_time_ms") and duration and on_progress:
                try:
                    seconds = float(value) / 1_000_000
                    frac = max(0.0, min(1.0, seconds / duration))
                    loop.call_soon_threadsafe(on_progress, frac)
                except ValueError:
                    pass
            elif key == "progress" and value == "end" and on_progress:
                loop.call_soon_threadsafe(on_progress, 1.0)

    def _read_stderr() -> None:
        nonlocal stderr_size
        assert proc.stderr is not None
        for line in proc.stderr:
            with stderr_lock:
                stderr_tail.append(line)
                stderr_size += len(line)
                while stderr_size > 4000 and stderr_tail:
                    stderr_size -= len(stderr_tail.pop(0))

    threads = [
        threading.Thread(target=_read_stdout, daemon=True),
        threading.Thread(target=_read_stderr, daemon=True),
    ]
    for t in threads:
        t.start()
    try:
        returncode = await asyncio.to_thread(proc.wait)
        for t in threads:
            t.join(timeout=2.0)
    finally:
        if register_proc:
            register_proc(None)

    with stderr_lock:
        stderr_text = "".join(stderr_tail)
    if log_path is not None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(chr(10).join([" ".join(cmd), stderr_text, ""]))
        except OSError as e:
            _log.warning("写入渲染日志失败: %s", e)

    if returncode != 0:
        tail = stderr_text.strip()[-RENDER_ERROR_TAIL:] or f"ffmpeg 退出码 {returncode}"
        raise RuntimeError(tail)


def availability_snapshot() -> dict[str, object]:
    """返回探测结果快照（GET /api/composer/config 用）。"""
    return {
        "ffmpeg_available": ffmpeg_available,
        "ffprobe_available": ffprobe_available,
        "ffmpeg_path": ffmpeg_path,
        "ffprobe_path": ffprobe_path,
        "error": last_probe_error,
    }
