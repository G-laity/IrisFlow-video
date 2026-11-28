"""一键启动两个本地模型 sidecar（CosyVoice + Stable Audio）。

- 两个 sidecar 各自运行在自己的 Python 3.10 venv 中；本脚本只负责启动、等待
  HTTP 就绪、日志落盘和统一停止，不启动后端。
- 模型仍然是懒加载：/health 就绪只代表 HTTP 服务已启动，第一次 TTS/BGM 请求
  才会加载权重。
- 日志写到 <repo>/logs/sidecars/<name>.log，后端通过
  GET /api/composer/sidecars 读取健康状态和日志尾部。
- 已经健康运行的 sidecar 会被复用，不会重复启动。

用法：
    python deploy/start_sidecars.py
    uv run python deploy/start_sidecars.py

环境变量：
    SIDECAR_HOME             默认 <repo 的上一级>/IrisFlow-sidecars
    COSYVOICE_PORT           默认 9701
    STABLE_AUDIO_PORT        默认 9702
    SIDECAR_STARTUP_TIMEOUT  等待 /health 的秒数，默认 30
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "logs" / "sidecars"
IS_WINDOWS = os.name == "nt"


def _startup_timeout() -> float:
    try:
        return float(os.environ.get("SIDECAR_STARTUP_TIMEOUT", "30"))
    except ValueError:
        return 30.0


@dataclass
class Spec:
    key: str
    label: str
    port: int
    model: str
    python: Path
    script: Path
    log: Path
    port_env: str


@dataclass
class Managed:
    spec: Spec
    proc: subprocess.Popen[bytes]
    log_file: BinaryIO


def sidecar_home() -> Path:
    raw = os.environ.get("SIDECAR_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    return (REPO_ROOT.parent / "IrisFlow-sidecars").resolve()


def _venv_python(home: Path, name: str) -> Path:
    if IS_WINDOWS:
        return home / name / ".venv" / "Scripts" / "python.exe"
    return home / name / ".venv" / "bin" / "python"


def build_specs(home: Path) -> list[Spec]:
    cosy_port = int(os.environ.get("COSYVOICE_PORT", "9701"))
    audio_port = int(os.environ.get("STABLE_AUDIO_PORT", "9702"))
    return [
        Spec(
            key="cosyvoice",
            label="CosyVoice",
            port=cosy_port,
            model="cosyvoice2",
            python=_venv_python(home, "cosyvoice"),
            script=REPO_ROOT / "deploy" / "cosyvoice" / "serve.py",
            log=LOG_DIR / "cosyvoice.log",
            port_env="COSYVOICE_PORT",
        ),
        Spec(
            key="stable_audio",
            label="Stable Audio",
            port=audio_port,
            model="stable-audio-open-small",
            python=_venv_python(home, "stable-audio"),
            script=REPO_ROOT / "deploy" / "stable-audio" / "serve.py",
            log=LOG_DIR / "stable-audio.log",
            port_env="STABLE_AUDIO_PORT",
        ),
    ]


def probe(port: int, timeout: float = 1.0) -> dict[str, object] | None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def log_line(text: str) -> None:
    print(f"[launcher] {text}", flush=True)


def _log_header(log_file: BinaryIO, text: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file.write(f"\n[launcher {stamp}] {text}\n".encode("utf-8"))
    log_file.flush()


def start(spec: Spec, home: Path) -> Managed | None:
    if not spec.python.is_file():
        log_line(f"{spec.label}: venv Python 不存在: {spec.python}")
        log_line(f"          先运行 deploy/{spec.key.replace('_', '-')}/setup.ps1")
        return None
    if not spec.script.is_file():
        log_line(f"{spec.label}: serve.py 不存在: {spec.script}")
        return None

    health = probe(spec.port)
    if health and health.get("model") == spec.model:
        log_line(f"{spec.label}: 已在 127.0.0.1:{spec.port} 运行，复用（不重复启动）")
        return None
    if health is not None:
        log_line(f"{spec.label}: 端口 {spec.port} 上的服务不是预期模型，跳过")
        return None
    if port_in_use(spec.port):
        log_line(f"{spec.label}: 端口 {spec.port} 已被其他进程占用，跳过（见该进程/日志）")
        return None

    spec.log.parent.mkdir(parents=True, exist_ok=True)
    log_file = spec.log.open("ab", buffering=0)
    _log_header(log_file, f"starting {spec.label} on 127.0.0.1:{spec.port}")

    env = os.environ.copy()
    env["SIDECAR_HOME"] = str(home)
    env[spec.port_env] = str(spec.port)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0

    try:
        proc = subprocess.Popen(
            [str(spec.python), str(spec.script)],
            cwd=str(spec.script.parent),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
    except OSError as exc:
        log_line(f"{spec.label}: 启动失败: {exc}")
        _log_header(log_file, f"start failed: {exc}")
        log_file.close()
        return None

    log_line(f"{spec.label}: 已启动 pid={proc.pid} port={spec.port} log={spec.log}")
    return Managed(spec, proc, log_file)


def wait_ready(item: Managed) -> bool:
    deadline = time.monotonic() + _startup_timeout()
    while time.monotonic() < deadline:
        if item.proc.poll() is not None:
            return False
        health = probe(item.spec.port)
        if health and health.get("model") == item.spec.model:
            log_line(f"{item.spec.label}: HTTP 就绪 {health}")
            return True
        time.sleep(0.5)
    log_line(f"{item.spec.label}: {_startup_timeout():.0f}s 内未就绪（进程仍在，详见日志）")
    return False


def _close_exited(item: Managed, code: int) -> None:
    _log_header(item.log_file, f"{item.spec.label} exited with code {code}")
    try:
        item.log_file.close()
    except OSError:
        pass
    log_line(f"{item.spec.label}: 进程退出 code={code}")


def monitor(managed: list[Managed]) -> int:
    """等待启动的 sidecar；某个退出时关闭其日志并继续照看其余的。"""
    finished_code = 0
    while managed:
        for item in list(managed):
            code = item.proc.poll()
            if code is not None:
                _close_exited(item, code)
                managed.remove(item)
                if code != 0 and finished_code == 0:
                    finished_code = code
        if not managed:
            break
        time.sleep(0.5)
    return finished_code


def stop(managed: list[Managed]) -> None:
    for item in managed:
        if item.proc.poll() is None:
            if IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/PID", str(item.proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                item.proc.terminate()
                try:
                    item.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    item.proc.kill()
            _log_header(item.log_file, f"stopped {item.spec.label}")
            log_line(f"{item.spec.label}: 已停止 pid={item.proc.pid}")
        try:
            item.proc.wait(timeout=5)
        except Exception:
            pass
        try:
            item.log_file.close()
        except OSError:
            pass
    managed.clear()


def _configure_console() -> None:
    """Windows 控制台默认编码可能是 GBK；统一按 UTF-8 输出中文。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass


def main() -> int:
    home = sidecar_home()
    log_line(f"sidecar home: {home}")
    log_line(f"logs: {LOG_DIR}")
    if not home.is_dir():
        log_line(f"SIDECAR_HOME 不存在: {home}；请先按 deploy/README.md 安装")
        return 1

    managed: list[Managed] = []
    try:
        for spec in build_specs(home):
            item = start(spec, home)
            if item is not None:
                managed.append(item)

        if not managed:
            log_line("没有需要启动的 sidecar（可能都已在运行，或路径缺失）")
            return 0

        for item in list(managed):
            if item.proc.poll() is not None:
                _close_exited(item, item.proc.returncode or 1)
                managed.remove(item)
            else:
                wait_ready(item)

        if not managed:
            log_line("sidecar 启动后立即退出，请查看日志")
            return 1

        log_line("按 Ctrl+C 停止；模型在首次 TTS/BGM 请求时加载")
        return monitor(managed)
    except KeyboardInterrupt:
        log_line("收到 Ctrl+C，正在停止...")
        return 130
    finally:
        stop(managed)


if __name__ == "__main__":
    _configure_console()
    sys.exit(main())
