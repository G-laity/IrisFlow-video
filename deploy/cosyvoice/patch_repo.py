"""对 CosyVoice 源码做 Windows / 推理环境的最小补丁。

1. `cosyvoice/dataset/processor.py` 中的 `import pyworld` 改为可选：
   pyworld 无 Windows wheel（需编译），且仅训练路径的 f0 提取使用；
   模型 yaml 会预解析该模块的符号，因此必须可导入。
   pyarrow 仍正常安装（有 Windows wheel）。

用法: python patch_repo.py <CosyVoice repo 路径>
"""

from __future__ import annotations

import pathlib
import sys

OLD = "import pyworld as pw"
NEW = (
    "try:\n"
    "    import pyworld as pw\n"
    "except ImportError:  # Windows / 推理环境无需 f0 提取\n"
    "    pw = None"
)

OLD_LOAD_WAV = """def load_wav(wav, target_sr, min_sr=16000):
    speech, sample_rate = torchaudio.load(wav, backend='soundfile')
    speech = speech.mean(dim=0, keepdim=True)"""
NEW_LOAD_WAV = """def load_wav(wav, target_sr, min_sr=16000):
    # torchaudio >= 2.9 的 load() 强制 torchcodec；改用 soundfile 直接读取
    import soundfile as sf
    data, sample_rate = sf.read(wav, dtype='float32', always_2d=True)
    speech = torch.from_numpy(data).mean(dim=1, keepdim=True).transpose(0, 1)"""



def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python patch_repo.py <repo>", file=sys.stderr)
        return 2
    repo = pathlib.Path(sys.argv[1])
    processor = repo / "cosyvoice" / "dataset" / "processor.py"
    if not processor.is_file():
        print(f"未找到: {processor}", file=sys.stderr)
        return 1
    text = processor.read_text(encoding="utf-8")
    if "pw = None" in text:
        print("processor.py 已打补丁，跳过")
    elif OLD not in text:
        print("processor.py 中未找到 pyworld 导入，跳过")
    else:
        processor.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
        print("已打补丁: pyworld 改为可选导入")

    file_utils = repo / "cosyvoice" / "utils" / "file_utils.py"
    utils_text = file_utils.read_text(encoding="utf-8")
    if "sf.read(wav" in utils_text:
        print("file_utils.py 已打补丁，跳过")
    elif OLD_LOAD_WAV not in utils_text:
        print("file_utils.py: load_wav 模式未匹配，跳过")
    else:
        file_utils.write_text(utils_text.replace(OLD_LOAD_WAV, NEW_LOAD_WAV, 1), encoding="utf-8")
        print("已打补丁: load_wav 改用 soundfile")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
