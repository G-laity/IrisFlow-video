"""素材服务 —— 下载 / 上传 / hash 去重 / 判型 / 探测 / 删除。

入库管线（URL 与上传共用）：
  流式写盘（边写边算 sha256）→ 去重（hash 命中直接复用已有素材）
  → MIME / 扩展名判型（仅媒体白名单）→ ffprobe 探测 → 入库。
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from pathlib import Path

import httpx
from fastapi import UploadFile

from composer import config as composer_config
from composer.ffmpeg import probe_media
from composer.store import composer_store
from llm.constants import (
    COMPOSER_HASH_CHUNK,
    COMPOSER_HTTP_TIMEOUT,
    COMPOSER_KIND_AUDIO,
    COMPOSER_KIND_IMAGE,
    COMPOSER_KIND_UNKNOWN,
    COMPOSER_KIND_VIDEO,
    COMPOSER_MAX_UPLOAD_SIZE,
    COMPOSER_MEDIA_EXTS,
    COMPOSER_SOURCE_UPLOAD,
    COMPOSER_SOURCE_URL,
)

_log = logging.getLogger(__name__)

# ── 路径 ──────────────────────────────────────────────────

_DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "composer"
_ASSETS_DIR: Path = _DATA_DIR / "assets"


def _ext_from_name(name: str) -> str:
    return Path(name).suffix.lower()


def _kind_hint_from_ext(ext: str) -> str:
    entry = COMPOSER_MEDIA_EXTS.get(ext)
    return entry[0] if entry else COMPOSER_KIND_UNKNOWN


def _ext_for_kind(kind: str, probe: dict[str, object], fallback_ext: str) -> str:
    """根据判型结果与探测信息挑选最终扩展名。"""
    if kind == COMPOSER_KIND_IMAGE and fallback_ext not in COMPOSER_MEDIA_EXTS:
        return ".png"
    if kind == COMPOSER_KIND_VIDEO:
        return ".mp4" if fallback_ext not in COMPOSER_MEDIA_EXTS else fallback_ext
    if kind == COMPOSER_KIND_AUDIO:
        return ".mp3" if fallback_ext not in COMPOSER_MEDIA_EXTS else fallback_ext
    return fallback_ext or ".bin"


def _finalize_kind(ext_hint: str, probe: dict[str, object]) -> str:
    """扩展名提示 + ffprobe 流信息双确认最终类型。

    probe_media 的输出约定：视频含 vcodec，纯音频含 acodec，
    图片仅含 width/height（图片 codec 已在 ffprobe 层识别剔除）。
    """
    if "vcodec" in probe:
        return COMPOSER_KIND_VIDEO
    if "acodec" in probe:
        return COMPOSER_KIND_AUDIO
    if "width" in probe and "height" in probe:
        return COMPOSER_KIND_IMAGE
    return ext_hint


def _hash_bucket_path(sha256: str, ext: str) -> Path:
    """hash 前 4 字符两两分桶：assets/ab/cd/<sha256>.<ext>"""
    return _ASSETS_DIR / sha256[:2] / sha256[2:4] / f"{sha256}{ext}"


async def _hash_and_save(
    src: httpx.Response | UploadFile, dest_dir: Path, ext: str, max_bytes: int
) -> tuple[str, int, Path]:
    """边读边写边算 sha256，返回 (sha256, 字节数, 临时文件路径)。

    src: httpx 响应流（.aiter_bytes()）或 UploadFile（.read()）。
    超过 max_bytes 抛 ValueError。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_dir / f".tmp_{uuid.uuid4().hex}{ext}"
    sha = hashlib.sha256()
    total = 0
    try:
        with open(tmp_path, "wb") as f:
            if isinstance(src, httpx.Response):
                async for chunk in src.aiter_bytes(COMPOSER_HASH_CHUNK):
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"素材超过大小上限（{max_bytes // (1024 * 1024)} MB）")
                    sha.update(chunk)
                    f.write(chunk)
            else:
                while True:
                    chunk = await src.read(COMPOSER_HASH_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"素材超过大小上限（{max_bytes // (1024 * 1024)} MB）")
                    sha.update(chunk)
                    f.write(chunk)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    if total == 0:
        tmp_path.unlink(missing_ok=True)
        raise ValueError("素材内容为空")
    return sha.hexdigest(), total, tmp_path


def _finalize_file(tmp_path: Path, sha256: str, ext: str) -> Path:
    """临时文件移动到 hash 分桶最终路径。"""
    final = _hash_bucket_path(sha256, ext)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.replace(final)
    return final


async def _ingest(
    src: httpx.Response | UploadFile,
    ext: str,
    source: str,
    url: str = "",
    meta: dict[str, object] | None = None,
) -> tuple[dict[str, object], bool]:
    """共用入库管线：写盘+hash → 去重 → 判型 → 探测 → 入库。

    Returns:
        (素材字典, 是否去重命中)。去重命中时复用已有素材记录。
    """
    if ext not in COMPOSER_MEDIA_EXTS:
        raise ValueError(f"不支持的媒体类型: {ext or '(无扩展名)'}")

    sha256, size_bytes, tmp_path = await _hash_and_save(
        src, _ASSETS_DIR, ext, COMPOSER_MAX_UPLOAD_SIZE
    )

    return await _ingest_hashed(sha256, size_bytes, tmp_path, ext, source, url, meta)


async def _ingest_hashed(
    sha256: str,
    size_bytes: int,
    tmp_path: Path,
    ext: str,
    source: str,
    url: str = "",
    meta: dict[str, object] | None = None,
) -> tuple[dict[str, object], bool]:
    """入库后半段：去重 → 判型 → 探测 → 入库。"""
    # hash 去重：命中直接复用已有素材（秒级返回）
    existing = await composer_store.find_by_sha256(sha256)
    if existing is not None:
        tmp_path.unlink(missing_ok=True)  # 清理本次临时文件（入库文件早已存在）
        _log.info("素材去重命中: %s（复用 %s）", sha256[:12], existing["asset_id"])
        return existing, True

    ext_hint = _kind_hint_from_ext(ext)

    # ffprobe 探测（ffmpeg 缺失时按扩展名判型降级）
    probe: dict[str, object] = {}
    probe_error = ""
    try:
        probe = await probe_media(str(tmp_path))
    except RuntimeError as e:
        probe_error = str(e)
        _log.warning("素材探测失败（按扩展名判型）: %s", probe_error)

    kind = _finalize_kind(ext_hint, probe) if probe else ext_hint
    if kind == COMPOSER_KIND_UNKNOWN:
        tmp_path.unlink(missing_ok=True)
        raise ValueError("无法识别素材类型（非图片 / 视频 / 音频）")

    final_path = _finalize_file(tmp_path, sha256, _ext_for_kind(kind, probe, ext))

    asset = await composer_store.add_asset(
        kind=kind,
        source=source,
        url=url,
        file_path=str(final_path.relative_to(_DATA_DIR)).replace("\\", "/"),
        sha256=sha256,
        size_bytes=size_bytes,
        probe=probe,
        meta={**(meta or {}), **({"probe_error": probe_error} if probe_error else {})},
    )
    return asset, False


async def import_from_url(url: str, kind: str | None = None) -> tuple[dict[str, object], bool]:
    """从 URL 下载素材入库（流式，hash 去重）。"""
    if not re.match(r"^https?://", url.strip()):
        raise ValueError("仅支持 http/https URL")

    timeout = httpx.Timeout(COMPOSER_HTTP_TIMEOUT, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url.strip()) as resp:
            if resp.status_code >= 400:
                raise ValueError(f"下载失败: HTTP {resp.status_code}（远程文件不存在或不可访问）")
            content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            # 从 URL 路径或 Content-Type 推断扩展名
            url_path = url.split("?")[0].split("#")[0]
            ext = _ext_from_name(url_path)
            if ext not in COMPOSER_MEDIA_EXTS:
                # 按 Content-Type 反查扩展名
                for cand_ext, (_, ct) in COMPOSER_MEDIA_EXTS.items():
                    if ct == content_type:
                        ext = cand_ext
                        break
            if kind is not None and kind in (COMPOSER_KIND_IMAGE, COMPOSER_KIND_VIDEO, COMPOSER_KIND_AUDIO):
                # 显式指定 kind 仅作为判型提示，最终以探测为准
                pass
            return await _ingest(resp, ext, COMPOSER_SOURCE_URL, url=url.strip())


async def import_from_bytes(
    data: bytes,
    ext: str,
    source: str,
    meta: dict[str, object] | None = None,
) -> tuple[dict[str, object], bool]:
    """从内存字节入库（TTS / 音乐生成产物），复用去重 + 探测管线。"""
    if not data:
        raise ValueError("生成结果为空")
    if len(data) > COMPOSER_MAX_UPLOAD_SIZE:
        raise ValueError(f"生成结果超过大小上限（{COMPOSER_MAX_UPLOAD_SIZE // (1024 * 1024)} MB）")
    if ext not in COMPOSER_MEDIA_EXTS:
        raise ValueError(f"不支持的媒体类型: {ext}")
    _ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = _ASSETS_DIR / f".tmp_{uuid.uuid4().hex}{ext}"
    tmp_path.write_bytes(data)
    sha256 = hashlib.sha256(data).hexdigest()
    return await _ingest_hashed(sha256, len(data), tmp_path, ext, source, "", meta)


async def import_from_upload(file: UploadFile, filename: str) -> tuple[dict[str, object], bool]:
    """从上传文件入库（流式写盘，500 MB 上限，仅媒体类型）。"""
    ext = _ext_from_name(filename or "")
    if ext not in COMPOSER_MEDIA_EXTS:
        raise ValueError(
            f"不支持的媒体类型: {ext or '(无扩展名)'}，仅支持图片 / 视频 / 音频"
        )
    # 预检大小（UploadFile.size 可用时）
    declared = getattr(file, "size", None)
    if isinstance(declared, int) and declared > COMPOSER_MAX_UPLOAD_SIZE:
        raise ValueError(
            f"文件过大（{declared // (1024 * 1024)} MB），上限 {COMPOSER_MAX_UPLOAD_SIZE // (1024 * 1024)} MB"
        )
    return await _ingest(
        file, ext, COMPOSER_SOURCE_UPLOAD,
        meta={"filename": filename or ""},
    )


def asset_abs_path(file_path: str) -> Path:
    """素材相对路径 → 绝对路径。"""
    return (_DATA_DIR / file_path).resolve()


async def delete_asset(asset_id: str) -> dict[str, object] | None:
    """删除素材：引用计数归零才删文件；被引用时仅提示。

    M1 无项目引用，ref_count 恒为 0 → 直接删文件。
    """
    asset = await composer_store.get_asset(asset_id)
    if asset is None:
        return None
    ref_count = await composer_store.get_ref_count(asset_id)
    if ref_count > 0:
        raise RuntimeError(f"素材被 {ref_count} 个项目引用，无法删除")
    deleted = await composer_store.delete_asset(asset_id)
    if deleted is not None:
        abs_path = asset_abs_path(str(deleted["file_path"]))
        try:
            abs_path.unlink(missing_ok=True)
        except OSError as e:
            _log.warning("素材文件删除失败（记录已删）: %s", e)
    return deleted


def disk_usage_bytes() -> int:
    """data/composer 目录总占用（字节）。"""
    if not _DATA_DIR.exists():
        return 0
    return sum(
        p.stat().st_size for p in _DATA_DIR.rglob("*")
        if p.is_file() and p.name != "composer.db"
    )


def disk_limit_bytes() -> int:
    """当前配置的磁盘水位上限（字节）。"""
    return composer_config.get_disk_limit_bytes()
