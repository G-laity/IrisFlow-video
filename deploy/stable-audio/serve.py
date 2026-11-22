"""Stable Audio Open Small sidecar —— BGM 生成 HTTP 服务。

契约（后端 composer/music.py）：
  POST /v1/audio/generate
    {"prompt": "轻快的电子氛围", "duration": 11}
    → 音频字节（mp3）
  GET /health → {"status": "ok", "model": "stable-audio-open-small"}

环境变量：
  STABLE_AUDIO_MODEL_DIR  模型目录（默认 <SIDECAR_HOME>/stable-audio/models/stable-audio-open-small）
  STABLE_AUDIO_PORT       监听端口（默认 9702）
  STABLE_AUDIO_STEPS      采样步数（默认 100；CPU 可降到 50 提速）
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

SIDECAR_HOME = Path(os.environ.get("SIDECAR_HOME", Path(__file__).resolve().parents[2].parent / "IrisFlow-sidecars"))
MODEL_DIR = Path(os.environ.get(
    "STABLE_AUDIO_MODEL_DIR",
    SIDECAR_HOME / "stable-audio" / "models" / "stable-audio-open-small",
))
PORT = int(os.environ.get("STABLE_AUDIO_PORT", "9702"))
STEPS = int(os.environ.get("STABLE_AUDIO_STEPS", "100"))

app = FastAPI(title="Stable Audio Sidecar")

_model = None
_model_config = None


def _get_model():
    """从本地目录加载模型（get_pretrained_model 只接受 HF repo id）。"""
    global _model, _model_config
    if _model is None:
        import json

        from stable_audio_tools.models.factory import create_model_from_config
        from stable_audio_tools.models.utils import load_ckpt_state_dict

        with open(MODEL_DIR / "model_config.json", encoding="utf-8") as f:
            _model_config = json.load(f)
        model = create_model_from_config(_model_config)
        weights = MODEL_DIR / "model.safetensors"
        if not weights.is_file():
            weights = MODEL_DIR / "model.ckpt"
        model.load_state_dict(load_ckpt_state_dict(str(weights)))
        _model = model.to("cuda" if _has_cuda() else "cpu").eval()
    return _model, _model_config


def _has_cuda() -> bool:
    import torch

    return torch.cuda.is_available()


class GenerateRequest(BaseModel):
    prompt: str
    duration: int | None = 11


@app.get("/health")
async def health():
    return {"status": "ok", "model": "stable-audio-open-small", "model_dir": str(MODEL_DIR)}


@app.post("/v1/audio/generate")
async def generate(req: GenerateRequest):
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt 为空")
    seconds = max(1, min(60, int(req.duration or 11)))
    try:
        from stable_audio_tools.inference.generation import generate_diffusion_cond

        import random

        model, cfg = _get_model()
        sample_rate = int(cfg.get("sample_rate", 44100))
        # 该模型为 rf_denoiser（rectified flow），支持 euler / rk4 / dpmpp / pingpong；
        # 显式传 seed 规避 numpy 2 下 generate_diffusion_cond 的 randint(2**32) 溢出。
        output = generate_diffusion_cond(
            model,
            steps=STEPS,
            cfg_scale=7,
            seed=random.randint(0, 2**31 - 2),
            conditioning=[{"prompt": prompt, "seconds_start": 0, "seconds_total": seconds}],
            sample_size=int(sample_rate * seconds),
            sampler_type="pingpong",
            device="cuda" if _has_cuda() else "cpu",
        )
        audio = output[0].cpu().squeeze(0)
    except Exception as e:  # noqa: BLE001 —— sidecar 边界
        raise HTTPException(status_code=500, detail=f"生成失败: {e}") from e

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)
    try:
        import soundfile as sf

        # audio: (channels, samples) → soundfile 需要 (frames, channels)
        sf.write(str(wav_path), audio.numpy().T, sample_rate, format="WAV")
        return Response(content=_wav_to_mp3(wav_path), media_type="audio/mpeg")
    finally:
        wav_path.unlink(missing_ok=True)


def _wav_to_mp3(wav_path: Path) -> bytes:
    import subprocess

    mp3_path = wav_path.with_suffix(".mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path),
             "-codec:a", "libmp3lame", "-q:a", "4", str(mp3_path)],
            check=True,
        )
        return mp3_path.read_bytes()
    finally:
        mp3_path.unlink(missing_ok=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
