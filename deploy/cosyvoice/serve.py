"""CosyVoice 2.5 sidecar —— OpenAI-compatible 语音合成 HTTP 服务。

契约（后端 composer/tts.py）：
  POST /v1/audio/speech
    {"input": "文本", "voice": "旁白·男", "speed": 1.0, "response_format": "mp3"}
    → 音频字节
  GET /health → {"status": "ok", "model": "cosyvoice2"}

环境变量：
  COSYVOICE_MODEL_DIR  模型目录（默认 <SIDECAR_HOME>/cosyvoice/models/CosyVoice2-0.5B）
  COSYVOICE_VOICES_DIR 提示音色 wav 目录（默认 <SIDECAR_HOME>/cosyvoice/voices）
  COSYVOICE_PORT       监听端口（默认 9701）
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

SIDECAR_HOME = Path(os.environ.get("SIDECAR_HOME", Path(__file__).resolve().parents[2].parent / "IrisFlow-sidecars"))
MODEL_DIR = Path(os.environ.get("COSYVOICE_MODEL_DIR", SIDECAR_HOME / "cosyvoice" / "models" / "CosyVoice2-0.5B"))
VOICES_DIR = Path(os.environ.get("COSYVOICE_VOICES_DIR", SIDECAR_HOME / "cosyvoice" / "voices"))
REPO_DIR = Path(os.environ.get("COSYVOICE_REPO_DIR", SIDECAR_HOME / "cosyvoice" / "repo"))
PORT = int(os.environ.get("COSYVOICE_PORT", "9701"))

# CosyVoice 未安装为包（setup 直接克隆源码），把 repo 根目录加入导入路径
if REPO_DIR.is_dir() and str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

app = FastAPI(title="CosyVoice Sidecar")

_model = None


def _get_model():
    global _model
    if _model is None:
        from cosyvoice.cli.cosyvoice import CosyVoice2  # 延迟导入（首次请求才加载）

        _model = CosyVoice2(str(MODEL_DIR), load_jit=False, load_trt=False, fp16=False)
    return _model


class SpeechRequest(BaseModel):
    input: str
    voice: str | None = None
    speed: float | None = 1.0
    response_format: str | None = "mp3"


@app.get("/health")
async def health():
    return {"status": "ok", "model": "cosyvoice2", "model_dir": str(MODEL_DIR)}


def _wav_bytes_to_mp3(wav_bytes: bytes) -> bytes:
    """wav → mp3（依赖 ffmpeg 命令行，与主项目环境一致）。"""
    import subprocess

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as src:
        src.write(wav_bytes)
        src_path = src.name
    dst_path = src_path.replace(".wav", ".mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", src_path, "-codec:a", "libmp3lame", dst_path],
            check=True,
        )
        return Path(dst_path).read_bytes()
    finally:
        Path(src_path).unlink(missing_ok=True)
        Path(dst_path).unlink(missing_ok=True)


@app.post("/v1/audio/speech")
async def speech(req: SpeechRequest):
    text = req.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input 为空")
    voice = req.voice or "default"
    prompt_wav = VOICES_DIR / f"{voice}.wav"
    if not prompt_wav.exists():
        prompt_wav = VOICES_DIR / "default.wav"
    if not prompt_wav.exists():
        raise HTTPException(
            status_code=503,
            detail=f"缺少提示音色: {prompt_wav}（请放入 3-10 秒 wav）",
        )
    try:
        model = _get_model()
        # zero-shot 克隆：用提示音色 + 参考文本
        prompt_text = ""  # CosyVoice2 允许空 prompt_text（跨语种模式）
        import soundfile as sf

        chunks: list[bytes] = []
        for out in model.inference_cross_lingual(text, str(prompt_wav), stream=False):
            wav_tensor = out["tts_speech"]
            buf = io.BytesIO()
            # torchaudio >= 2.9 的 save() 需要 torchcodec，改用 soundfile
            sf.write(buf, wav_tensor.squeeze(0).cpu().numpy().T, model.sample_rate, format="WAV")
            chunks.append(buf.getvalue())
        wav_bytes = b"".join(chunks)
    except Exception as e:  # noqa: BLE001 —— sidecar 边界，转 HTTP 错误
        raise HTTPException(status_code=500, detail=f"合成失败: {e}") from e

    if (req.response_format or "mp3") == "wav":
        return Response(content=wav_bytes, media_type="audio/wav")
    return Response(content=_wav_bytes_to_mp3(wav_bytes), media_type="audio/mpeg")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
