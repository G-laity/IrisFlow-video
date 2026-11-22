"""时间轴 Schema 校验 + SRT 生成。

时间轴结构见 PLAN.md §4.3。校验器返回逐字段中文错误，供 LLM 自纠重试；
前端编辑器同样展示这些错误。
"""

from __future__ import annotations

from llm.constants import (
    IMAGE_MAX_DURATION,
    IMAGE_MIN_DURATION,
    MOTION_KENBURNS,
    MOTION_STATIC,
    PAN_DOWN,
    PAN_LEFT,
    PAN_NONE,
    PAN_RIGHT,
    PAN_UP,
    ROLE_BGM,
    ROLE_NARRATION,
    SRT_TIMESTAMP_FORMAT,
    SUBTITLE_FONT,
    SUBTITLE_STYLE_DEFAULT,
    SUBTITLE_STYLES,
    TIMELINE_VERSION,
    TRACK_AUDIO,
    TRACK_SUBTITLES,
    TRACK_VIDEO,
    TRANSITION_TYPES,
    ZOOM_MAX,
    ZOOM_MIN,
)

_VALID_PANS = {PAN_NONE, PAN_LEFT, PAN_RIGHT, PAN_UP, PAN_DOWN}
_VALID_ROLES = {ROLE_NARRATION, ROLE_BGM}
_VALID_MOTIONS = {MOTION_KENBURNS, MOTION_STATIC}


def _as_float(value: object, default: float | None = None) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def validate_timeline(
    timeline: object,
    assets: list[dict[str, object]],
    presets: dict[str, dict[str, int]],
) -> list[str]:
    """校验时间轴，返回错误列表（空列表 = 合法）。

    Args:
        timeline: 时间轴 dict。
        assets: 素材库全量素材（用于存在性与探测时长校验）。
        presets: 分辨率预设表。
    """
    errors: list[str] = []
    if not isinstance(timeline, dict):
        return ["timeline 必须是 JSON 对象"]

    if int(_as_float(timeline.get("version"), 0) or 0) != TIMELINE_VERSION:
        errors.append(f"tracks.version 必须为 {TIMELINE_VERSION}")
    preset = timeline.get("preset")
    if not isinstance(preset, str) or preset not in presets:
        errors.append(f"preset 无效: {preset!r}（可选: {', '.join(presets)}）")

    tracks = timeline.get("tracks")
    if not isinstance(tracks, dict):
        return errors + ["tracks 必须是对象，包含 video / audio / subtitles 三个数组"]

    asset_map: dict[str, dict[str, object]] = {
        str(a.get("asset_id")): a for a in assets if a.get("asset_id")
    }

    # ── video 轨 ──────────────────────────────────
    video = tracks.get(TRACK_VIDEO)
    if not isinstance(video, list) or not video:
        errors.append("tracks.video 必须是非空数组（至少一个镜头）")
        video = []
    prev_duration: float | None = None
    for i, seg in enumerate(video):
        prefix = f"tracks.video[{i}]"
        if not isinstance(seg, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        asset_id = str(seg.get("asset_id") or "")
        asset = asset_map.get(asset_id)
        if asset is None:
            errors.append(f"{prefix}.asset_id 不存在: {asset_id!r}")
        else:
            kind = asset.get("kind")
            if kind not in ("video", "image"):
                errors.append(f"{prefix}.asset_id 类型不符: {kind}（需要 video 或 image）")
        duration = _as_float(seg.get("duration"))
        if duration is None or duration <= 0:
            errors.append(f"{prefix}.duration 必须为正数（秒）")
            duration = None
        elif asset is not None:
            kind = asset.get("kind")
            raw_probe = asset.get("probe")
            probe: dict[str, object] = raw_probe if isinstance(raw_probe, dict) else {}
            probed = _as_float(probe.get("duration"))
            if kind == "image":
                if not (IMAGE_MIN_DURATION <= duration <= IMAGE_MAX_DURATION):
                    errors.append(
                        f"{prefix}.duration 超出图片镜头范围 [{IMAGE_MIN_DURATION}, {IMAGE_MAX_DURATION}] 秒: {duration}"
                    )
            elif probed is not None and duration > probed + 0.01:
                errors.append(
                    f"{prefix}.duration {duration}s 超过素材探测时长 {probed}s"
                )
        trim_in = _as_float(seg.get("trim_in"), 0.0) or 0.0
        if trim_in < 0:
            errors.append(f"{prefix}.trim_in 不能为负数")
        transition = seg.get("transition_in")
        if isinstance(transition, dict):
            t_type = transition.get("type")
            if t_type is not None and str(t_type) not in TRANSITION_TYPES:
                errors.append(
                    f"{prefix}.transition_in.type 无效: {t_type!r}（fade / dissolve / slide）"
                )
            t_dur = _as_float(transition.get("duration"), 0.0) or 0.0
            if t_dur < 0:
                errors.append(f"{prefix}.transition_in.duration 不能为负数")
            if duration is not None and t_dur >= duration:
                errors.append(
                    f"{prefix}.transition_in.duration {t_dur}s 必须小于本段时长 {duration}s"
                )
            if prev_duration is not None and t_dur >= prev_duration:
                errors.append(
                    f"{prefix}.transition_in.duration {t_dur}s 必须小于前一段时长 {prev_duration}s"
                )
        motion = seg.get("motion")
        if isinstance(motion, dict):
            m_type = motion.get("type")
            if m_type is not None and str(m_type) not in _VALID_MOTIONS:
                errors.append(f"{prefix}.motion.type 无效: {m_type!r}（kenburns / static）")
            pan = motion.get("pan")
            if pan is not None and str(pan) not in _VALID_PANS:
                errors.append(f"{prefix}.motion.pan 无效: {pan!r}")
            from_zoom = _as_float(motion.get("from_zoom"), 1.0)
            to_zoom = _as_float(motion.get("to_zoom"), 1.0)
            if from_zoom is None or not (ZOOM_MIN <= from_zoom <= ZOOM_MAX):
                errors.append(f"{prefix}.motion.from_zoom 必须在 [{ZOOM_MIN}, {ZOOM_MAX}]")
            if to_zoom is None or not (ZOOM_MIN <= to_zoom <= ZOOM_MAX):
                errors.append(f"{prefix}.motion.to_zoom 必须在 [{ZOOM_MIN}, {ZOOM_MAX}]")
            if from_zoom is not None and to_zoom is not None and to_zoom < from_zoom:
                errors.append(f"{prefix}.motion.to_zoom 不能小于 from_zoom")
        prev_duration = duration

    # ── audio 轨 ──────────────────────────────────
    audio = tracks.get(TRACK_AUDIO, [])
    if not isinstance(audio, list):
        errors.append("tracks.audio 必须是数组")
        audio = []
    for i, trk in enumerate(audio):
        prefix = f"tracks.audio[{i}]"
        if not isinstance(trk, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        role = trk.get("role")
        if str(role) not in _VALID_ROLES:
            errors.append(f"{prefix}.role 无效: {role!r}（narration / bgm）")
        asset_id = str(trk.get("asset_id") or "")
        asset = asset_map.get(asset_id)
        if asset is None:
            errors.append(f"{prefix}.asset_id 不存在: {asset_id!r}")
        elif asset.get("kind") != "audio":
            errors.append(f"{prefix}.asset_id 类型不符: {asset.get('kind')}（需要 audio）")
        start = _as_float(trk.get("start"), 0.0) or 0.0
        if start < 0:
            errors.append(f"{prefix}.start 不能为负数")
        dur = _as_float(trk.get("duration"), 0.0) or 0.0
        if dur <= 0:
            errors.append(f"{prefix}.duration 必须为正数")
        ducking = trk.get("ducking")
        if ducking is not None and not isinstance(ducking, bool):
            errors.append(f"{prefix}.ducking 必须是布尔值")

    # ── subtitles 轨 ──────────────────────────────
    subtitles = tracks.get(TRACK_SUBTITLES, [])
    if not isinstance(subtitles, list):
        errors.append("tracks.subtitles 必须是数组")
        subtitles = []
    for i, sub in enumerate(subtitles):
        prefix = f"tracks.subtitles[{i}]"
        if not isinstance(sub, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        start = _as_float(sub.get("start"))
        end = _as_float(sub.get("end"))
        if start is None or end is None:
            errors.append(f"{prefix} 的 start / end 必须是数字（秒）")
        elif start < 0 or end <= start:
            errors.append(f"{prefix} 时间区间非法: start={start}, end={end}（需 0 ≤ start < end）")
        if not str(sub.get("text") or "").strip():
            errors.append(f"{prefix}.text 不能为空")
        style = sub.get("style")
        if style is not None and str(style) not in SUBTITLE_STYLES:
            errors.append(
                f"{prefix}.style 无效: {style!r}（可选: {', '.join(SUBTITLE_STYLES)}）"
            )

    return errors


def generate_srt(subtitles: list[dict[str, object]]) -> str:
    """时间轴字幕 → SRT 文本。"""
    lines: list[str] = []
    index = 1
    for sub in subtitles:
        start = _as_float(sub.get("start"), 0.0) or 0.0
        end = _as_float(sub.get("end"), 0.0) or 0.0
        text = str(sub.get("text") or "").replace("\r\n", "\n").strip()
        if end <= start or not text:
            continue
        lines.append(str(index))
        lines.append(f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}")
        lines.append(text)
        lines.append("")
        index += 1
    return "\n".join(lines)


def generate_ass(subtitles: list[dict[str, object]], width: int, height: int) -> str:
    """时间轴字幕 → ASS（M4 样式化字幕）。"""
    lines: list[str] = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
    ]
    for name, spec in SUBTITLE_STYLES.items():
        lines.append(
            f"Style: {name},{SUBTITLE_FONT},{spec['size']},"
            "&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
            "0,0,0,0,100,100,0,0,1,"
            f"{spec['outline']},0,{spec['alignment']},40,40,{spec['margin_v']},1"
        )
    lines += [
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for sub in subtitles:
        start = _as_float(sub.get("start"), 0.0) or 0.0
        end = _as_float(sub.get("end"), 0.0) or 0.0
        if end <= start:
            continue
        text = str(sub.get("text") or "").replace("\r\n", "\n").replace("\n", "\\N").strip()
        if not text:
            continue
        # 避免被 libass 当成 override 标签
        text = text.replace("{", "(").replace("}", ")")
        style = str(sub.get("style") or SUBTITLE_STYLE_DEFAULT)
        if style not in SUBTITLE_STYLES:
            style = SUBTITLE_STYLE_DEFAULT
        lines.append(f"Dialogue: 0,{_fmt_ass_time(start)},{_fmt_ass_time(end)},{style},,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def _fmt_ass_time(seconds: float) -> str:
    """ASS 时间格式：H:MM:SS.cc（厘秒）。"""
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _fmt_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return SRT_TIMESTAMP_FORMAT % (h, m, s, ms)


def timeline_asset_ids(timeline: object) -> list[str]:
    """提取时间轴引用的全部 asset_id（去重，保持出现顺序）。"""
    if not isinstance(timeline, dict):
        return []
    tracks = timeline.get("tracks")
    if not isinstance(tracks, dict):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for key in (TRACK_VIDEO, TRACK_AUDIO):
        entries = tracks.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            aid = str(entry.get("asset_id") or "")
            if aid and aid not in seen:
                seen.add(aid)
                result.append(aid)
    return result


def empty_timeline(preset: str) -> dict[str, object]:
    """空时间轴骨架（新建项目默认值）。"""
    return {
        "version": TIMELINE_VERSION,
        "preset": preset,
        "tracks": {TRACK_VIDEO: [], TRACK_AUDIO: [], TRACK_SUBTITLES: []},
    }
