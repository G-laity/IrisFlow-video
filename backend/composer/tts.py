"""语音合成服务层。

Provider 降级链（PLAN §8.4）：
  local-http（CosyVoice sidecar）→ openai-compat（SiliconFlow 等云端）→ edge-tts（免费兜底）。

local-http 与 openai-compat 共用 OpenAI-compatible 契约：
  POST {base_url}/audio/speech
  {"model"?, "input": text, "voice": voice, "speed": speed, "response_format": "mp3"}
  → 音频字节。
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
import tempfile
from pathlib import Path

import httpx

from composer import config as composer_config
from llm.constants import (
    MSG_TTS_SPLIT_FAILED,
    TTS_HTTP_TIMEOUT,
    TTS_OUTPUT_FORMAT,
    TTS_PROVIDER_EDGE,
    TTS_PROVIDER_LOCAL,
    TTS_PROVIDER_OPENAI,
    TTS_SPLIT_DELIMITERS,
    TTS_SPLIT_MAX_CHARS,
    TTS_SPEECH_PATH,
)

_log = logging.getLogger(__name__)

EDGE_DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


def edge_available() -> bool:
    """edge-tts 是否已安装。"""
    return importlib.util.find_spec("edge_tts") is not None


def _provider_chain() -> list[dict[str, object]]:
    """按优先级构建 provider 链：primary → fallback → edge。"""
    cfg = composer_config.get_tts()
    chain: list[dict[str, object]] = [cfg]
    fallback = cfg.get("fallback")
    if isinstance(fallback, dict) and fallback.get("provider"):
        chain.append(fallback)
    if edge_available():
        chain.append({"provider": TTS_PROVIDER_EDGE})
    return chain


async def _synth_http(
    provider: dict[str, object], text: str, voice: str, speed: float
) -> tuple[bytes, str]:
    base_url = str(provider.get("base_url") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("base_url 未配置")
    token = composer_config.resolve_secret(str(provider.get("token") or ""))
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    model = str(provider.get("model") or "")
    payload: dict[str, object] = {
        "input": text,
        "voice": voice,
        "speed": speed,
        "response_format": TTS_OUTPUT_FORMAT,
    }
    if model:
        payload["model"] = model
    timeout = httpx.Timeout(TTS_HTTP_TIMEOUT, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}{TTS_SPEECH_PATH}", json=payload, headers=headers)
        if resp.status_code >= 400:
            body = resp.text[:300]
            raise RuntimeError(f"HTTP {resp.status_code}: {body}")
        if not resp.content:
            raise RuntimeError("返回内容为空")
    return resp.content, TTS_OUTPUT_FORMAT


async def _synth_edge(text: str, voice: str, speed: float) -> tuple[bytes, str]:
    if not edge_available():
        raise RuntimeError("edge-tts 未安装")
    import edge_tts  # 延迟导入（仅兜底时使用）

    rate_pct = int(round((speed - 1.0) * 100))
    rate = f"{rate_pct:+d}%"
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        communicate = edge_tts.Communicate(text, voice or EDGE_DEFAULT_VOICE, rate=rate)
        await communicate.save(str(tmp_path))
        data = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)
    if not data:
        raise RuntimeError("edge-tts 返回内容为空")
    return data, "mp3"


async def _synthesize_one(
    text: str, voice: str | None, speed: float | None
) -> tuple[bytes, str, str]:
    """单段文本合成（provider 降级链）。"""
    cfg = composer_config.get_tts()
    named_voice = voice or str(cfg.get("default_voice") or "")
    raw_voices = cfg.get("voices")
    voices: dict[str, object] = raw_voices if isinstance(raw_voices, dict) else {}
    mapped_voice = str(voices.get(named_voice, named_voice))
    if speed is not None:
        rate = speed
    else:
        try:
            rate = float(cfg.get("speed") or 1.0)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            rate = 1.0

    errors: list[str] = []
    for provider in _provider_chain():
        kind = str(provider.get("provider") or "")
        try:
            if kind == TTS_PROVIDER_EDGE:
                data, ext = await _synth_edge(text, mapped_voice or EDGE_DEFAULT_VOICE, rate)
            elif kind in (TTS_PROVIDER_LOCAL, TTS_PROVIDER_OPENAI):
                data, ext = await _synth_http(provider, text, mapped_voice, rate)
            else:
                raise RuntimeError(f"未知 provider: {kind}")
            _log.info("语音合成成功: provider=%s chars=%d bytes=%d", kind, len(text), len(data))
            return data, ext, kind
        except Exception as e:
            _log.warning("语音 provider '%s' 失败: %s", kind, e)
            errors.append(f"{kind}: {e}")
    raise RuntimeError("全部语音 provider 失败 → " + " | ".join(errors))


def _split_sentences(text: str) -> list[str]:
    """按中英文标点/换行切句。"""
    parts: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in TTS_SPLIT_DELIMITERS:
            if buf.strip():
                parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    return parts


def split_text(text: str, max_chars: int = TTS_SPLIT_MAX_CHARS) -> list[str]:
    """按句合并为 ≤ max_chars 的片段；超长单句硬切。"""
    chunks: list[str] = []
    current = ""
    for sentence in _split_sentences(text):
        while len(sentence) > max_chars:
            chunks.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if not sentence:
            continue
        if current and len(current) + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        chunks.append(current)
    return chunks


async def _concat_audio(parts: list[bytes]) -> bytes:
    """用 ffmpeg 把多段音频拼接为一个 mp3。"""
    from composer import ffmpeg as composer_ffmpeg

    if not composer_ffmpeg.ffmpeg_available:
        raise RuntimeError("ffmpeg 不可用，无法拼接分句音频")
    tmpdir = Path(tempfile.mkdtemp(prefix="iris_tts_"))
    try:
        names: list[str] = []
        for i, data in enumerate(parts):
            name = f"part_{i:03d}.mp3"
            (tmpdir / name).write_bytes(data)
            names.append(name)
        (tmpdir / "list.txt").write_text(
            chr(10).join(f"file '{n}'" for n in names), encoding="utf-8"
        )
        cmd = [
            composer_ffmpeg.ffmpeg_path, "-xerror", "-y",
            "-f", "concat", "-safe", "0", "-i", "list.txt",
            "-c:a", "libmp3lame", "-q:a", "4", "merged.mp3",
        ]
        await composer_ffmpeg.run_ffmpeg(cmd, cwd=tmpdir)
        return (tmpdir / "merged.mp3").read_bytes()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


async def synthesize(
    text: str,
    voice: str | None = None,
    speed: float | None = None,
    split: bool = True,
) -> tuple[bytes, str, str]:
    """合成语音（M4：长文本自动分句合成后拼接）。

    Returns:
        (音频字节, 扩展名, 实际使用的 provider)。
    """
    text = (text or "").strip()
    if not text:
        raise RuntimeError("合成文本为空")
    if split and len(text) > TTS_SPLIT_MAX_CHARS:
        chunks = split_text(text)
        if len(chunks) > 1:
            _log.info("长文本分句合成: %d 段（%d 字）", len(chunks), len(text))
            audio_parts: list[bytes] = []
            provider = ""
            try:
                for chunk in chunks:
                    data, _, provider = await _synthesize_one(chunk, voice, speed)
                    audio_parts.append(data)
                return await _concat_audio(audio_parts), "mp3", provider
            except Exception as e:
                raise RuntimeError(f"{MSG_TTS_SPLIT_FAILED}: {e}") from None
    return await _synthesize_one(text, voice, speed)


async def synthesize_dialogue(
    segments: list[dict[str, object]], speed: float | None = None
) -> tuple[bytes, str, str]:
    """多说话人对话合成：逐段指定音色，拼接为单条音频。"""
    if not segments:
        raise RuntimeError("对话片段为空")
    parts: list[bytes] = []
    provider = ""
    for seg in segments:
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        voice = seg.get("voice")
        data, _, provider = await synthesize(
            text, str(voice) if voice else None, speed, split=True
        )
        parts.append(data)
    if not parts:
        raise RuntimeError("对话片段均为空文本")
    if len(parts) == 1:
        return parts[0], "mp3", provider
    return await _concat_audio(parts), "mp3", provider


async def probe() -> dict[str, object]:
    """探测 TTS 各 provider 连通性（供 GET /api/composer/config）。"""
    cfg = composer_config.get_tts()
    fallback = cfg.get("fallback") if isinstance(cfg.get("fallback"), dict) else {}
    primary: dict[str, object] = {
        "provider": cfg.get("provider"),
        "base_url": cfg.get("base_url"),
        "reachable": await _reachable(str(cfg.get("base_url") or "")),
    }
    fallback_info = None
    if isinstance(fallback, dict) and fallback.get("base_url"):
        fallback_info = {
            "provider": fallback.get("provider"),
            "base_url": fallback.get("base_url"),
            "reachable": await _reachable(str(fallback.get("base_url") or "")),
        }
    return {
        "primary": primary,
        "fallback": fallback_info,
        "edge_available": edge_available(),
    }


async def _reachable(base_url: str) -> bool:
    """connect 成功即视为可达（不要求 /health 返回 2xx）。"""
    if not base_url:
        return False
    base = base_url.rstrip("/")
    root = base[:-3] if base.endswith("/v1") else base
    try:
        async with httpx.AsyncClient(timeout=_probe_timeout()) as client:
            await client.get(f"{root}/health")
        return True
    except Exception:
        return False


def _probe_timeout() -> httpx.Timeout:
    from llm.constants import PROVIDER_PROBE_TIMEOUT
    return httpx.Timeout(PROVIDER_PROBE_TIMEOUT, connect=PROVIDER_PROBE_TIMEOUT)
