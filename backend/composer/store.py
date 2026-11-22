"""ComposerStore —— 合成器持久化存储。

SQLite（data/composer/composer.db）三表：projects / assets / renders。
沿用 llm/sessions.py 模式：每次新建连接、asyncio.Lock 单写者、busy_timeout。
M1 仅 assets 表读写，projects / renders 表建好待 M2/M3 启用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path

from llm.constants import (
    COMPOSER_ID_LENGTH,
    COMPOSER_ID_PREFIX_ASSET,
    SQLITE_BUSY_TIMEOUT,
)

_log = logging.getLogger(__name__)

# ── 存储路径 ──────────────────────────────────────────────

_DB_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "composer" / "composer.db"


def _get_db() -> sqlite3.Connection:
    """获取数据库连接（每次新建，线程安全）。"""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT}")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            source TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            file_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            probe TEXT NOT NULL DEFAULT '{}',
            meta TEXT NOT NULL DEFAULT '{}',
            ref_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            script TEXT NOT NULL DEFAULT '',
            timeline TEXT NOT NULL DEFAULT '{}',
            asset_ids TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS renders (
            render_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            state TEXT NOT NULL,
            progress REAL NOT NULL DEFAULT 0,
            stage_detail TEXT NOT NULL DEFAULT '{}',
            output_path TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            finished_at REAL
        )"""
    )
    conn.commit()
    return conn


# ── 行转字典 ──────────────────────────────────────────────

_ASSET_COLS = (
    "asset_id, kind, source, url, file_path, sha256, size_bytes, probe, meta, ref_count, created_at"
)


def _row_to_asset(row: tuple[object, ...]) -> dict[str, object]:
    asset_id, kind, source, url, file_path, sha256, size_bytes, probe, meta, ref_count, created_at = row

    def _parse_json(raw: object) -> dict[str, object]:
        text = raw if isinstance(raw, str) else ""
        try:
            obj = json.loads(text) if text else {}
            return obj if isinstance(obj, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    probe_obj = _parse_json(probe)
    meta_obj = _parse_json(meta)
    return {
        "asset_id": asset_id,
        "kind": kind,
        "source": source,
        "url": url,
        "file_path": file_path,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "probe": probe_obj,
        "meta": meta_obj,
        "ref_count": ref_count,
        "created_at": created_at,
    }


class ComposerStore:
    """合成器存储：SQLite 持久化 + 单写者锁。"""

    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        _get_db()  # 启动即建表

    # ── 素材（M1）─────────────────────────────────────

    async def add_asset(
        self,
        kind: str,
        source: str,
        url: str,
        file_path: str,
        sha256: str,
        size_bytes: int,
        probe: dict[str, object],
        meta: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """新增素材记录，返回完整素材字典。"""
        asset_id = COMPOSER_ID_PREFIX_ASSET + uuid.uuid4().hex[:COMPOSER_ID_LENGTH]
        async with self._lock:
            conn = _get_db()
            conn.execute(
                """INSERT INTO assets
                   (asset_id, kind, source, url, file_path, sha256, size_bytes, probe, meta, ref_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                (asset_id, kind, source, url, file_path, sha256, size_bytes,
                 json.dumps(probe, ensure_ascii=False),
                 json.dumps(meta or {}, ensure_ascii=False),
                 time.time()),
            )
            conn.commit()
            conn.close()
        asset = await self.get_asset(asset_id)
        assert asset is not None
        _log.info("素材入库: %s kind=%s size=%d", asset_id, kind, size_bytes)
        return asset

    async def get_asset(self, asset_id: str) -> dict[str, object] | None:
        async with self._lock:
            conn = _get_db()
            row = conn.execute(
                f"SELECT {_ASSET_COLS} FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            conn.close()
            return _row_to_asset(row) if row else None

    async def find_by_sha256(self, sha256: str) -> dict[str, object] | None:
        """按内容 hash 查找已有素材（去重命中）。"""
        async with self._lock:
            conn = _get_db()
            row = conn.execute(
                f"SELECT {_ASSET_COLS} FROM assets WHERE sha256 = ?", (sha256,)
            ).fetchone()
            conn.close()
            return _row_to_asset(row) if row else None

    async def list_assets(self, kind: str | None = None) -> list[dict[str, object]]:
        async with self._lock:
            conn = _get_db()
            if kind:
                rows = conn.execute(
                    f"SELECT {_ASSET_COLS} FROM assets WHERE kind = ? ORDER BY created_at DESC",
                    (kind,),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {_ASSET_COLS} FROM assets ORDER BY created_at DESC"
                ).fetchall()
            conn.close()
            return [_row_to_asset(r) for r in rows]

    async def delete_asset(self, asset_id: str) -> dict[str, object] | None:
        """删除素材记录（调用方负责引用计数与文件清理判断）。"""
        asset = await self.get_asset(asset_id)
        if asset is None:
            return None
        async with self._lock:
            conn = _get_db()
            conn.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))
            conn.commit()
            conn.close()
        _log.info("素材删除: %s", asset_id)
        return asset

    # ── 引用计数（M2 项目引用时使用）────────────────────

    async def incr_ref(self, asset_id: str) -> None:
        async with self._lock:
            conn = _get_db()
            conn.execute("UPDATE assets SET ref_count = ref_count + 1 WHERE asset_id = ?", (asset_id,))
            conn.commit()
            conn.close()

    async def decr_ref(self, asset_id: str) -> int:
        """引用计数减一，返回最新值。"""
        async with self._lock:
            conn = _get_db()
            conn.execute(
                "UPDATE assets SET ref_count = MAX(0, ref_count - 1) WHERE asset_id = ?",
                (asset_id,),
            )
            row = conn.execute(
                "SELECT ref_count FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            conn.commit()
            conn.close()
            return int(row[0]) if row else 0

    async def get_ref_count(self, asset_id: str) -> int:
        async with self._lock:
            conn = _get_db()
            row = conn.execute(
                "SELECT ref_count FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            conn.close()
            return int(row[0]) if row else 0

    # ── 预留（M2/M3 启用）─────────────────────────────

    def _new_id(self, prefix: str) -> str:
        return prefix + uuid.uuid4().hex[:COMPOSER_ID_LENGTH]


# 模块级单例
composer_store = ComposerStore()
