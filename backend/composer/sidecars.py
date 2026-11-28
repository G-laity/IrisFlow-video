"""本地模型 sidecar 健康与日志快照。

进程由 ``deploy/start_sidecars.py`` 启动，后端不负责拉起/停止，只通过：

- ``GET http://127.0.0.1:<port>/health`` 获取健康；
- ``<repo>/logs/sidecars/<name>.log`` 读取启动器写入的日志尾部。

这样后端进程重启、``--reload`` 都不会影响 sidecar 的生命周期。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from composer import config as composer_config
from llm.constants import (
    MUSIC_DEFAULT_PORT,
    PROVIDER_PROBE_TIMEOUT,
    TTS_DEFAULT_PORT,
)

LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "sidecars"
MAX_LOG_LINES = 500
LOG_TAIL_BYTES = 96 * 1024


@dataclass(frozen=True)
class SidecarSpec:
    key: str
    label: str
    port: int
    model: str
    config_section: str
    log_name: str
    port_env: str


SIDECARS: tuple[SidecarSpec, ...] = (
    SidecarSpec(
        key="cosyvoice",
        label="CosyVoice",
        port=TTS_DEFAULT_PORT,
        model="cosyvoice2",
        config_section="tts",
        log_name="cosyvoice.log",
        port_env="COSYVOICE_PORT",
    ),
    SidecarSpec(
        key="stable_audio",
        label="Stable Audio",
        port=MUSIC_DEFAULT_PORT,
        model="stable-audio-open-small",
        config_section="music",
        log_name="stable-audio.log",
        port_env="STABLE_AUDIO_PORT",
    ),
)


def _is_local_base(base_url: str) -> bool:
    return "127.0.0.1" in base_url or "localhost" in base_url


def _local_base(spec: SidecarSpec) -> str:
    """优先用 composer 配置里的本地 base_url；配置成云端时回退到默认本地端口。"""
    cfg = (
        composer_config.get_tts()
        if spec.config_section == "tts"
        else composer_config.get_music()
    )
    configured = str(cfg.get("base_url") or "").rstrip("/")
    if configured and _is_local_base(configured):
        return configured[:-3] if configured.endswith("/v1") else configured
    port = int(os.environ.get(spec.port_env, spec.port))
    return f"http://127.0.0.1:{port}"


def _tail(path: Path, max_lines: int) -> list[str]:
    """读取文件末尾若干行（限制字节数，避免大日志占内存）。"""
    try:
        if not path.is_file():
            return []
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - LOG_TAIL_BYTES))
            raw = fh.read()
        text = raw.decode("utf-8", errors="replace")
        return text.splitlines()[-max_lines:]
    except OSError:
        return []


async def snapshot(lines: int = 120) -> dict[str, object]:
    """返回两个本地 sidecar 的健康状态和日志尾部。"""
    max_lines = max(1, min(MAX_LOG_LINES, int(lines)))
    timeout = httpx.Timeout(PROVIDER_PROBE_TIMEOUT, connect=PROVIDER_PROBE_TIMEOUT)
    results: dict[str, object] = {}

    async with httpx.AsyncClient(timeout=timeout) as client:
        for spec in SIDECARS:
            base = _local_base(spec)
            health_url = f"{base}/health"
            health: dict[str, object] | None = None
            error: str | None = None
            reachable = False
            model_ok = False
            try:
                resp = await client.get(health_url)
                resp.raise_for_status()
                payload: object = resp.json()
                if isinstance(payload, dict):
                    health = payload
                    model_ok = payload.get("model") == spec.model
                else:
                    health = {"raw": payload}
                reachable = True
            except Exception as exc:  # noqa: BLE001 - sidecar 边界
                error = str(exc) or exc.__class__.__name__

            log_path = LOG_DIR / spec.log_name
            results[spec.key] = {
                "name": spec.key,
                "label": spec.label,
                "port": spec.port,
                "base_url": base,
                "health_url": health_url,
                "expected_model": spec.model,
                "reachable": reachable,
                "model_ok": model_ok,
                "health": health,
                "error": error,
                "log_path": str(log_path),
                "log_tail": _tail(log_path, max_lines),
            }

    return {
        "log_dir": str(LOG_DIR),
        "lines": max_lines,
        "sidecars": results,
    }
