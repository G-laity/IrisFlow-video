"""合成器配置。

持久化到 data/composer_config.json，走 AppConfig 模式（默认值 + 文件覆盖，
运行时通过 apply_* 修改并写回文件）。不依赖 .env。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from llm.constants import (
    COMPOSER_DISK_LIMIT_BYTES,
    COMPOSER_PRESETS,
    COMPOSER_RENDER_CONCURRENCY,
    ENCODING_AUDIO_BITRATE_DEFAULT,
    ENCODING_CRF_DEFAULT,
    ENCODING_PRESET_DEFAULT,
    MUSIC_DEFAULT_DURATION,
    MUSIC_DEFAULT_PORT,
    MUSIC_OUTPUT_FORMAT,
    TTS_DEFAULT_PORT,
    TTS_OUTPUT_FORMAT,
    TTS_PROVIDER_LOCAL,
)

_log = logging.getLogger(__name__)

# ── 配置键 ────────────────────────────────────────────────

KEY_FFMPEG_PATH = "ffmpeg_path"
KEY_DISK_LIMIT_BYTES = "disk_limit_bytes"
KEY_RENDER_CONCURRENCY = "render_concurrency"
KEY_PRESETS = "presets"
KEY_TTS = "tts"
KEY_MUSIC = "music"
KEY_ENCODING = "encoding"

ENCODING_DEFAULTS: dict[str, object] = {
    "preset": ENCODING_PRESET_DEFAULT,
    "crf": ENCODING_CRF_DEFAULT,
    "audio_bitrate": ENCODING_AUDIO_BITRATE_DEFAULT,
}

# ── TTS / 音乐默认配置（PLAN §8.4）─────────────────────────

TTS_DEFAULTS: dict[str, object] = {
    "provider": TTS_PROVIDER_LOCAL,
    "base_url": f"http://127.0.0.1:{TTS_DEFAULT_PORT}/v1",
    "fallback": {},
    "default_voice": "旁白·男",
    "speed": 1.0,
    "voices": {"旁白·男": "zh-CN-YunxiNeural", "旁白·女": "zh-CN-XiaoxiaoNeural"},
    "output_format": TTS_OUTPUT_FORMAT,
}

MUSIC_DEFAULTS: dict[str, object] = {
    "provider": TTS_PROVIDER_LOCAL,
    "base_url": f"http://127.0.0.1:{MUSIC_DEFAULT_PORT}/v1",
    "duration": MUSIC_DEFAULT_DURATION,
    "output_format": MUSIC_OUTPUT_FORMAT,
}

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "composer_config.json"


def _load_file() -> dict[str, object]:
    try:
        if _CONFIG_PATH.exists():
            raw = json.loads(_CONFIG_PATH.read_text("utf-8"))
            if isinstance(raw, dict):
                return raw
    except Exception as e:
        _log.debug("加载合成器配置失败（首次运行正常）: %s", e)
    return {}


def _save_file(data: dict[str, object]) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    except Exception as e:
        _log.warning("保存合成器配置失败: %s", e)


_persisted = _load_file()


def _int_or(value: object, default: int) -> int:
    """安全整数转换（非法值回退默认）。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ── 运行期值（模块级缓存，apply 时更新）────────────────────

_ffmpeg_path = str(_persisted.get(KEY_FFMPEG_PATH, ""))
_disk_limit_bytes = _int_or(_persisted.get(KEY_DISK_LIMIT_BYTES), COMPOSER_DISK_LIMIT_BYTES)
_render_concurrency = _int_or(_persisted.get(KEY_RENDER_CONCURRENCY), COMPOSER_RENDER_CONCURRENCY)
_presets: dict[str, dict[str, int]] = {
    str(k): {str(kk): int(vv) for kk, vv in v.items()}
    for k, v in _persisted.get(KEY_PRESETS, COMPOSER_PRESETS).items()  # type: ignore[union-attr]
} or dict(COMPOSER_PRESETS)


def _merge_defaults(defaults: dict[str, object], raw: object) -> dict[str, object]:
    """以默认值为底合并持久化配置（保留未知键，嵌套 dict 浅合并）。"""
    merged = dict(defaults)
    if isinstance(raw, dict):
        for k, v in raw.items():
            key = str(k)
            if isinstance(v, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **v}  # type: ignore[dict-item]
            else:
                merged[key] = v
    return merged


_tts_cfg: dict[str, object] = _merge_defaults(TTS_DEFAULTS, _persisted.get(KEY_TTS))
_music_cfg: dict[str, object] = _merge_defaults(MUSIC_DEFAULTS, _persisted.get(KEY_MUSIC))
_encoding_cfg: dict[str, object] = _merge_defaults(ENCODING_DEFAULTS, _persisted.get(KEY_ENCODING))


def get_ffmpeg_path() -> str:
    """返回配置的自定义 ffmpeg 路径（可为空 = 走 PATH 探测）。"""
    return _ffmpeg_path


def get_disk_limit_bytes() -> int:
    """返回 data/composer 磁盘水位上限（字节）。"""
    return _disk_limit_bytes


def get_render_concurrency() -> int:
    """返回渲染并发数（M3 启用）。"""
    return _render_concurrency


def get_presets() -> dict[str, dict[str, int]]:
    """返回分辨率预设表副本。"""
    return {k: dict(v) for k, v in _presets.items()}


def get_tts() -> dict[str, object]:
    """返回 TTS 配置副本。"""
    return json.loads(json.dumps(_tts_cfg, ensure_ascii=False))


def get_music() -> dict[str, object]:
    """返回音乐配置副本。"""
    return json.loads(json.dumps(_music_cfg, ensure_ascii=False))


def get_encoding() -> dict[str, object]:
    """返回编码参数（preset / crf / audio_bitrate）。"""
    return json.loads(json.dumps(_encoding_cfg, ensure_ascii=False))


def resolve_secret(text: str) -> str:
    """解析 ${VAR} 密钥引用（复用全局密钥库）。"""
    from core.config import resolve_secret_text  # 延迟导入避免循环
    return resolve_secret_text(text)


def snapshot() -> dict[str, object]:
    """返回完整配置快照（GET /api/composer/config 用）。"""
    return {
        KEY_FFMPEG_PATH: _ffmpeg_path,
        KEY_DISK_LIMIT_BYTES: _disk_limit_bytes,
        KEY_RENDER_CONCURRENCY: _render_concurrency,
        KEY_PRESETS: {k: dict(v) for k, v in _presets.items()},
        KEY_TTS: get_tts(),
        KEY_MUSIC: get_music(),
        KEY_ENCODING: get_encoding(),
    }


def apply(updates: dict[str, object]) -> dict[str, object]:
    """合并更新并持久化，返回更新后的快照。

    仅接受已知键；非法类型回退到默认值。
    """
    global _ffmpeg_path, _disk_limit_bytes, _render_concurrency, _presets, _tts_cfg, _music_cfg
    global _encoding_cfg
    if KEY_FFMPEG_PATH in updates:
        _ffmpeg_path = str(updates[KEY_FFMPEG_PATH] or "").strip()
    if KEY_TTS in updates and isinstance(updates[KEY_TTS], dict):
        _tts_cfg = _merge_defaults(_tts_cfg, updates[KEY_TTS])
    if KEY_MUSIC in updates and isinstance(updates[KEY_MUSIC], dict):
        _music_cfg = _merge_defaults(_music_cfg, updates[KEY_MUSIC])
    if KEY_ENCODING in updates and isinstance(updates[KEY_ENCODING], dict):
        _encoding_cfg = _merge_defaults(_encoding_cfg, updates[KEY_ENCODING])
    if KEY_DISK_LIMIT_BYTES in updates:
        _disk_limit_bytes = max(100 * 1024 * 1024, _int_or(updates[KEY_DISK_LIMIT_BYTES], COMPOSER_DISK_LIMIT_BYTES))
    if KEY_RENDER_CONCURRENCY in updates:
        _render_concurrency = max(1, min(4, _int_or(updates[KEY_RENDER_CONCURRENCY], COMPOSER_RENDER_CONCURRENCY)))
    if KEY_PRESETS in updates:
        raw = updates[KEY_PRESETS]
        if isinstance(raw, dict):
            cleaned: dict[str, dict[str, int]] = {}
            for name, spec in raw.items():
                if isinstance(spec, dict) and all(k in spec for k in ("width", "height", "fps")):
                    cleaned[str(name)] = {
                        "width": _int_or(spec.get("width"), 0),
                        "height": _int_or(spec.get("height"), 0),
                        "fps": _int_or(spec.get("fps"), 30),
                    }
            if cleaned:
                _presets = cleaned

    _save_file(snapshot())
    return snapshot()
