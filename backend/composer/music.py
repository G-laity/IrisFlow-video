"""背景音乐生成服务层。

Sidecar 契约（Stable Audio Open Small）：
  POST {base_url}/audio/generate
  {"prompt": 风格描述, "duration": 秒}
  → 音频字节。

无云端兜底：服务不可用时调用方返回引导信息（上传 BGM / 配置 sidecar），
不阻塞时间轴编排。
"""

from __future__ import annotations

import logging

import httpx

from composer import config as composer_config
from llm.constants import (
    MUSIC_GENERATE_PATH,
    MUSIC_HTTP_TIMEOUT,
    MUSIC_OUTPUT_FORMAT,
    PROVIDER_PROBE_TIMEOUT,
)

_log = logging.getLogger(__name__)


def _probe_timeout() -> httpx.Timeout:
    return httpx.Timeout(PROVIDER_PROBE_TIMEOUT, connect=PROVIDER_PROBE_TIMEOUT)


def _int_or(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


async def generate(prompt: str, duration: int | None = None) -> tuple[bytes, str]:
    """生成 BGM 片段。

    Args:
        prompt: 风格 / 情绪描述。
        duration: 时长（秒），空 = 配置默认值（11）。

    Returns:
        (音频字节, 扩展名)。

    Raises:
        RuntimeError: 服务不可用或生成失败。
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("缺失音乐风格描述")
    cfg = composer_config.get_music()
    base_url = str(cfg.get("base_url") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("music.base_url 未配置")
    secs = duration if duration else _int_or(cfg.get("duration"), 11)
    secs = max(1, min(60, int(secs)))
    payload = {"prompt": prompt, "duration": secs}

    timeout = httpx.Timeout(MUSIC_HTTP_TIMEOUT, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url}{MUSIC_GENERATE_PATH}", json=payload)
    except httpx.HTTPError as e:
        raise RuntimeError(f"音乐服务不可达: {e}") from None
    if resp.status_code >= 400:
        raise RuntimeError(f"音乐服务返回 HTTP {resp.status_code}: {resp.text[:300]}")
    if not resp.content:
        raise RuntimeError("音乐服务返回内容为空")
    _log.info("音乐生成成功: prompt=%r duration=%ds bytes=%d", prompt, secs, len(resp.content))
    return resp.content, MUSIC_OUTPUT_FORMAT


async def probe() -> dict[str, object]:
    """探测音乐服务连通性（供 GET /api/composer/config）。"""
    cfg = composer_config.get_music()
    base_url = str(cfg.get("base_url") or "")
    base = base_url.rstrip("/")
    root = base[:-3] if base.endswith("/v1") else base
    reachable = False
    if base:
        try:
            async with httpx.AsyncClient(timeout=_probe_timeout()) as client:
                await client.get(f"{root}/health")
            reachable = True
        except Exception:
            reachable = False
    return {
        "provider": cfg.get("provider"),
        "base_url": base_url,
        "reachable": reachable,
    }
