# 本地模型 Sidecar 部署

视频合成器 M2 的语音（TTS）与背景音乐（BGM）生成可选用本地模型。这些模型是 torch 栈、
锁定较低 Python 版本，与后端（Python 3.14）不兼容，因此以**独立进程 + HTTP 服务**运行
（sidecar 模式）。后端仅通过 httpx 访问 `http://127.0.0.1:<端口>`。

| Sidecar | 端口 | 用途 | 后端配置 |
|---|---|---|---|
| CosyVoice 2.5 | 9701 | 中文旁白合成 | `tts.base_url = http://127.0.0.1:9701/v1` |
| Stable Audio Open Small | 9702 | 背景音乐片段（~11s） | `music.base_url = http://127.0.0.1:9702/v1` |

## 目录约定

脚本与权重分离（权重不进仓库）：

```
E:\NT\IrisFlow-video\deploy\        # 脚本（git 管理，轻量）
E:\NT\IrisFlow-sidecars\            # ← 默认 SIDECAR_HOME（本机私有，数 GB）
├── python310\                      # CPython 3.10.11（华为镜像安装包，两个 sidecar 共用）
├── .uv-cache\                      # uv wheel 缓存（两个 sidecar 共享，torch 只存一份）
├── cosyvoice\
│   ├── .venv\                      # Python 3.10 + torch cu128 + 依赖
│   ├── repo\                       # CosyVoice 源码
│   ├── models\CosyVoice2-0.5B\
│   └── voices\                     # 提示音色 wav（3-10s，default.wav）
└── stable-audio\
    ├── .venv\
    └── models\stable-audio-open-small\
```

> **下载一次 / 磁盘一份**：`setup.ps1` 默认设置 `UV_CACHE_DIR=<SIDECAR_HOME>\.uv-cache` 和
> `UV_LINK_MODE=hardlink`。同版本 wheel 只下载一次；两个 venv 里的 torch 是同一份物理文件的
> 硬链接（缓存与 venv 同在 SIDECAR_HOME 所在盘）。若该盘不支持硬链接，去掉 `UV_LINK_MODE`
> 即退回复制（多占约 5-7 GB）。

> uv 下载的 Python 3.10 解释器在用户缓存（`%LOCALAPPDATA%\uv\python`，约 80 MB）。

换盘或换目录时用环境变量覆盖：

```powershell
$env:SIDECAR_HOME = "D:\models\IrisFlow-sidecars"
```

## 磁盘占用（2026-11-22 实测，两个 GPU sidecar）

| 组件 | 实测 |
|---|---|
| `python310\`（两个 sidecar 共用） | ~0.1 GB |
| `cosyvoice\.venv`（torch 2.9.1+cu128） | 5.1 GB |
| `cosyvoice\models\CosyVoice2-0.5B` | 5.3 GB（仓库含多个 checkpoint） |
| `cosyvoice\repo` | ~0.05 GB |
| `stable-audio\.venv`（torch 2.7.1+cu128 + stable-audio-tools） | 5.7 GB |
| `stable-audio\models\stable-audio-open-small` | 1.6 GB |
| `.uv-cache` + 其他 | ~2.3 GB |
| **合计** | **≈ 20 GB** |

> 两个 venv 的 torch 版本不同（2.9.1 / 2.7.1），无法硬链接共享，各占一份 CUDA 运行库。
> 零安装方案（edge-tts 旁白 + 上传 BGM）仍然可用，不占额外磁盘。

## 国内源（setup.ps1 默认启用）

| 用途 | 默认源 | 覆盖变量 |
|---|---|---|
| PyPI（普通 pip 包） | 清华 `https://pypi.tuna.tsinghua.edu.cn/simple` | `PYPI_INDEX_URL` |
| PyTorch wheel | 上海交大 `https://mirror.sjtu.edu.cn/pytorch-wheels/<cu128>`，按 **whl 直链**安装（该目录是扁平文件列表，非包索引） | `TORCH_INDEX_URL` / `TORCH_VERSION` |
| Python 3.10.11 安装包 | 华为云 `https://mirrors.huaweicloud.com/python/3.10.11/python-3.10.11-amd64.exe`（静默安装到 `<SIDECAR_HOME>\python310`） | `PYTHON310_URL` |
| Stable Audio 权重 | ModelScope 官方镜像（匿名可下，无需 token） | — |
| HuggingFace 模型（备用） | `https://hf-mirror.com`（gated 仓库需 `HF_TOKEN`） | `HF_ENDPOINT` / `HF_TOKEN` |
| CosyVoice 源码 | **Gitee 镜像** `https://gitee.com/mirrors/CosyVoice.git`（GitHub 直连国内不可用） | `COSYVOICE_REPO` |
| CosyVoice 权重 | ModelScope（国内直连） | — |

> **CosyVoice 依赖兼容性**（Windows + RTX 50 系实测结论）：
> - 仓库自带 `requirements.txt` 固定 `torch==2.3.1`（cu121），不支持 Blackwell → 改用裁剪清单，
>   锁定 `torch==2.9.1+cu128`（SJTU 索引，`--no-deps` 安装，纯 Python 依赖单独装）
> - `matcha-tts` 的 Cython 扩展需要 MSVC Build Tools，但该扩展仅训练用 → setup 把 matcha
>   源码内置到 venv 并打补丁（清空 `utils/__init__`、替换 `pylogger` 的 lightning 依赖）
> - `openai-whisper` 用 20250625（旧版 20231117 构建失败），走 PyPI
> - `pyworld`（训练）、`deepspeed`/`tensorrt`（Linux）、`gradio`/`tensorboard`/`lightning`（训练/演示）已排除
>
> **Stable Audio 兼容性**（Windows + RTX 50 系实测）：
> - `stable-audio-tools` 的依赖会把 torch 降级为 CPU 版 → 安装顺序改为最后用 SJTU 直链覆盖
>   `torch/torchaudio/torchvision`（2.7.1 / 0.22.1 + cu128）
> - PyWavelets 1.4.1 与 numpy 2 不兼容 → 升级 ≥1.8；LoRA 回调需要 `pytorch-lightning`
> - 模型的 diffusion objective 是 `rf_denoiser`，采样器用 `pingpong`（`dpmpp-3m-sde` 不支持）
> - numpy 2 下 `np.random.randint(0, 2**32)` 溢出 → serve.py 显式传 seed

所有变量都可预先设置后运行 setup，例如：

```powershell
$env:HF_TOKEN = "hf_xxx"
$env:CUDA_TAG = "cu128"
```

## 前置条件

| 项 | 说明 | 当前机器状态 |
|---|---|---|
| uv | 安装依赖（uv pip + 硬链接去重） | ✅ 已装 |
| 本机 Python | 3.10 由脚本从华为镜像下载安装包静默安装到 `<SIDECAR_HOME>\python310`，无需预装 | ✅ 3.13（不影响 sidecar） |
| 国内 CPython 镜像 | 华为云 `mirrors.huaweicloud.com/python/`（Gitee/GitHub 的 standalone 构建不可达） | ✅ 可用 |
| NVIDIA 驱动 | RTX 50 系（Blackwell）需 **CUDA 12.8+ 的 torch 轮子** | ✅ 驱动 576.65（满足） |
| 磁盘 | CosyVoice ~2-4 GB、Stable Audio ~1-2 GB（模型 + venv） | 待确认 |
| Hugging Face 访问 | Stable Audio 模型需先接受 license 并配置 `HF_TOKEN` | ❌ 未配置 |

> **RTX 50 系注意**：Blackwell（sm_120）只能用 `cu128` 及以上的 torch（≥ 2.7）。
> `setup.ps1` 已默认 `CUDA_TAG=cu128`；老显卡可 `$env:CUDA_TAG="cu124"`。
>
> **Stable Audio 模型下载**：先到 <https://huggingface.co/stabilityai/stable-audio-open-small>
> 接受许可，然后 `$env:HF_TOKEN="hf_..."` 再运行 setup。

## 部署步骤（Windows PowerShell）

```powershell
# 1. 语音（需要 NVIDIA GPU + CUDA；RTX 5060 8GB 可跑 CosyVoice2-0.5B）
cd deploy\cosyvoice
.\setup.ps1

# 2. 背景音乐（CPU 可跑，341M 模型）
cd ..\stable-audio
.\setup.ps1
```

首次运行会下载数 GB 权重，耗时较长。`setup.ps1` 只做一次性安装；启动服务：

```powershell
# 终端 1 — 语音
cd deploy\cosyvoice; .\serve.ps1

# 终端 2 — 背景音乐
cd deploy\stable-audio; .\serve.ps1
```

## 验证连通

```powershell
curl http://127.0.0.1:9701/health   # {"status":"ok","model":"cosyvoice2"}
curl http://127.0.0.1:9702/health   # {"status":"ok","model":"stable-audio-open-small"}
```

后端 `GET /api/composer/config` 的 `providers` 字段会显示各 provider 的 `reachable` 状态，
合成器面板的素材页也会显示服务可用性。

## 降级链（无需 sidecar 也能工作）

- **语音**：local-http（CosyVoice）→ openai-compat（SiliconFlow / OpenAI 兼容端点）→ **edge-tts**（免费兜底，随后端安装，仅需联网）。
  未部署 sidecar 时，只要后端能联网即可用 edge-tts 出旁白。
- **音乐**：无云端兜底。未部署 Stable Audio 时，`composer_bgm` 会返回引导信息，
  改为上传 / URL 导入现成 BGM 即可，不阻塞编排。

### ACE-Step 主题曲（M4 可选）

任何实现以下契约的 sidecar 都可直接接入，无需改后端代码：

```
POST {music.base_url}/audio/generate   {"prompt": "...", "duration": 180}
  → 音频字节（mp3）
GET  {music.base_url 去掉 /v1}/health
```

ACE-Step（3.5B，GPU 8-12 GB）部署后把 `music.base_url` 指向其适配服务即可生成完整主题曲；
RTX 5060 8 GB 属于踩线配置，可能需要量化或降档。

## 配置云端 TTS（可选，无 GPU 时推荐）

在 `backend/data/composer_config.json`（或设置面板后续版本）中：

```jsonc
{
  "tts": {
    "provider": "openai-compat",
    "base_url": "https://api.siliconflow.cn/v1",
    "token": "${TTS_TOKEN}",
    "model": "FunAudioLLM/CosyVoice2-0.5B",
    "default_voice": "旁白·女",
    "voices": { "旁白·男": "alex", "旁白·女": "anna" }
  }
}
```

`${TTS_TOKEN}` 在 `backend/data/secrets.json` 中定义（设置面板「密钥」标签页）。
