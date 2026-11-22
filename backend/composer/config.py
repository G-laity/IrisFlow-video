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
)

_log = logging.getLogger(__name__)

# ── 配置键 ────────────────────────────────────────────────

KEY_FFMPEG_PATH = "ffmpeg_path"
KEY_DISK_LIMIT_BYTES = "disk_limit_bytes"
KEY_RENDER_CONCURRENCY = "render_concurrency"
KEY_PRESETS = "presets"

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


def snapshot() -> dict[str, object]:
    """返回完整配置快照（GET /api/composer/config 用）。"""
    return {
        KEY_FFMPEG_PATH: _ffmpeg_path,
        KEY_DISK_LIMIT_BYTES: _disk_limit_bytes,
        KEY_RENDER_CONCURRENCY: _render_concurrency,
        KEY_PRESETS: {k: dict(v) for k, v in _presets.items()},
    }


def apply(updates: dict[str, object]) -> dict[str, object]:
    """合并更新并持久化，返回更新后的快照。

    仅接受已知键；非法类型回退到默认值。
    """
    global _ffmpeg_path, _disk_limit_bytes, _render_concurrency, _presets
    if KEY_FFMPEG_PATH in updates:
        _ffmpeg_path = str(updates[KEY_FFMPEG_PATH] or "").strip()
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
