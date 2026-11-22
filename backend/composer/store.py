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
    COMPOSER_ID_PREFIX_PROJECT,
    PROJECT_DEFAULT_TITLE,
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


_PROJECT_COLS = "project_id, title, script, timeline, asset_ids, created_at, updated_at"


def _parse_json_obj(raw: object, fallback: object) -> object:
    text = raw if isinstance(raw, str) else ""
    try:
        return json.loads(text) if text else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def _row_to_project(row: tuple[object, ...]) -> dict[str, object]:
    project_id, title, script, timeline, asset_ids, created_at, updated_at = row
    timeline_obj = _parse_json_obj(timeline, {})
    ids_obj = _parse_json_obj(asset_ids, [])
    return {
        "project_id": project_id,
        "title": title,
        "script": script,
        "timeline": timeline_obj if isinstance(timeline_obj, dict) else {},
        "asset_ids": [str(x) for x in ids_obj] if isinstance(ids_obj, list) else [],
        "created_at": created_at,
        "updated_at": updated_at,
    }


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

    # ── 项目（M2）─────────────────────────────────────

    async def create_project(
        self,
        title: str = PROJECT_DEFAULT_TITLE,
        script: str = "",
        timeline: dict[str, object] | None = None,
        asset_ids: list[str] | None = None,
    ) -> dict[str, object]:
        project_id = COMPOSER_ID_PREFIX_PROJECT + uuid.uuid4().hex[:COMPOSER_ID_LENGTH]
        now = time.time()
        async with self._lock:
            conn = _get_db()
            conn.execute(
                """INSERT INTO projects
                   (project_id, title, script, timeline, asset_ids, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (project_id, title, script,
                 json.dumps(timeline or {}, ensure_ascii=False),
                 json.dumps(asset_ids or [], ensure_ascii=False),
                 now, now),
            )
            conn.commit()
            conn.close()
        project = await self.get_project(project_id)
        assert project is not None
        _log.info("项目创建: %s title=%s", project_id, title)
        return project

    async def get_project(self, project_id: str) -> dict[str, object] | None:
        async with self._lock:
            conn = _get_db()
            row = conn.execute(
                f"SELECT {_PROJECT_COLS} FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            conn.close()
            return _row_to_project(row) if row else None

    async def list_projects(self) -> list[dict[str, object]]:
        async with self._lock:
            conn = _get_db()
            rows = conn.execute(
                f"SELECT {_PROJECT_COLS} FROM projects ORDER BY updated_at DESC"
            ).fetchall()
            conn.close()
            return [_row_to_project(r) for r in rows]

    async def update_project(
        self,
        project_id: str,
        title: str | None = None,
        script: str | None = None,
        timeline: dict[str, object] | None = None,
        asset_ids: list[str] | None = None,
    ) -> dict[str, object] | None:
        """更新项目字段（None = 保持不变），返回更新后的项目。"""
        existing = await self.get_project(project_id)
        if existing is None:
            return None
        new_title = title if title is not None else str(existing["title"])
        new_script = script if script is not None else str(existing["script"])
        new_timeline = timeline if timeline is not None else existing["timeline"]
        new_ids = asset_ids if asset_ids is not None else existing["asset_ids"]
        async with self._lock:
            conn = _get_db()
            conn.execute(
                """UPDATE projects SET title = ?, script = ?, timeline = ?, asset_ids = ?, updated_at = ?
                   WHERE project_id = ?""",
                (new_title, new_script,
                 json.dumps(new_timeline, ensure_ascii=False),
                 json.dumps(new_ids, ensure_ascii=False),
                 time.time(), project_id),
            )
            conn.commit()
            conn.close()
        _log.info("项目更新: %s", project_id)
        return await self.get_project(project_id)

    async def delete_project(self, project_id: str) -> dict[str, object] | None:
        project = await self.get_project(project_id)
        if project is None:
            return None
        async with self._lock:
            conn = _get_db()
            conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            conn.commit()
            conn.close()
        _log.info("项目删除: %s", project_id)
        return project


# 模块级单例
composer_store = ComposerStore()
