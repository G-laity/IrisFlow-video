"""合成器磁盘维护：占用快照 + LRU 回收（M5）。

回收顺序：
  1. 未被项目引用的素材（ref_count = 0，按创建时间升序）
  2. 已完成的旧渲染产物（按创建时间升序，删文件 + 记录）
直到占用 ≤ limit × target_ratio。
"""

from __future__ import annotations

import logging

from composer import assets as composer_assets
from composer import config as composer_config
from composer.store import composer_store
from llm.constants import RENDER_COMPLETED

_log = logging.getLogger(__name__)


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


async def usage_snapshot() -> dict[str, object]:
    """返回占用 / 上限 / 目标水位 / 是否启用自动清理。"""
    used = composer_assets.disk_usage_bytes()
    limit = composer_config.get_disk_limit_bytes()
    ratio = composer_config.get_disk_cleanup_target_ratio()
    return {
        "used_bytes": used,
        "limit_bytes": limit,
        "target_ratio": ratio,
        "target_bytes": int(limit * ratio),
        "cleanup_enabled": composer_config.get_disk_cleanup_enabled(),
    }


async def run_cleanup(force: bool = False) -> dict[str, object]:
    """执行 LRU 回收；force=True 时忽略“未启用”开关（手动触发）。"""
    if not force and not composer_config.get_disk_cleanup_enabled():
        return {
            "skipped": True,
            "reason": "disabled",
            "freed_bytes": 0,
            "deleted_assets": 0,
            "deleted_renders": 0,
        }

    used = composer_assets.disk_usage_bytes()
    limit = composer_config.get_disk_limit_bytes()
    target = int(limit * composer_config.get_disk_cleanup_target_ratio())
    if used <= target:
        return {
            "skipped": True,
            "reason": "below_target",
            "freed_bytes": 0,
            "deleted_assets": 0,
            "deleted_renders": 0,
        }

    freed = 0
    deleted_assets = 0
    deleted_renders = 0

    # ① 未引用素材
    all_assets = await composer_store.list_assets()
    unref = [a for a in all_assets if _int(a.get("ref_count")) == 0]
    unref.sort(key=lambda a: _num(a.get("created_at")))
    for asset in unref:
        if used <= target:
            break
        path = composer_assets.asset_abs_path(str(asset["file_path"]))
        size = path.stat().st_size if path.is_file() else 0
        try:
            deleted = await composer_assets.delete_asset(str(asset["asset_id"]))
        except RuntimeError:
            continue
        if deleted is None:
            continue
        freed += size
        deleted_assets += 1
        used -= size

    # ② 旧渲染产物
    if used > target:
        renders = [
            r for r in await composer_store.list_renders()
            if str(r["state"]) == RENDER_COMPLETED and r.get("output_path")
        ]
        renders.sort(key=lambda r: _num(r.get("created_at")))
        for render in renders:
            if used <= target:
                break
            path = composer_assets.asset_abs_path(str(render["output_path"]))
            size = path.stat().st_size if path.is_file() else 0
            path.unlink(missing_ok=True)
            await composer_store.delete_render(str(render["render_id"]))
            freed += size
            deleted_renders += 1
            used -= size

    _log.info(
        "磁盘清理完成: freed=%d bytes, assets=%d, renders=%d, used=%d/%d",
        freed, deleted_assets, deleted_renders, used, limit,
    )
    return {
        "skipped": False,
        "freed_bytes": freed,
        "deleted_assets": deleted_assets,
        "deleted_renders": deleted_renders,
        "used_bytes": used,
        "limit_bytes": limit,
        "target_bytes": target,
    }
