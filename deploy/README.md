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
<repo>\deploy\                      # setup / serve / start_sidecars 脚本（git 管理，轻量）
<SIDECAR_HOME>\                     # 默认 <repo 上一级>\IrisFlow-sidecars（与仓库同级，不在仓库内；不存在时自动创建；数 GB）
├── python-3.10.11-amd64.exe        # setup 下载的 Python 安装包（安装后可删）
├── python310\                      # Python 3.10.11 安装目录（两个 sidecar 共用）
├── .uv-cache\                      # uv wheel 缓存（两个 sidecar 共享，torch 只存一份）
├── cosyvoice\
│   ├── .venv\                      # Python 3.10 venv（setup 创建）
│   ├── repo\                       # CosyVoice 源码（Gitee 克隆）
│   ├── models\CosyVoice2-0.5B\     # 权重（ModelScope 下载）
│   └── voices\                     # 提示音色 wav（setup 复制 default.wav）
└── stable-audio\
    ├── .venv\                      # Python 3.10 venv（setup 创建）
    └── models\stable-audio-open-small\  # 权重（ModelScope / HuggingFace）
```

> **下载一次 / 磁盘一份**：`setup.ps1` 默认设置 `UV_CACHE_DIR=<SIDECAR_HOME>\.uv-cache` 和
> `UV_LINK_MODE=hardlink`。同版本 wheel 只下载一次；两个 venv 里的 torch 是同一份物理文件的
> 硬链接（缓存与 venv 同在 SIDECAR_HOME 所在盘）。若该盘不支持硬链接，去掉 `UV_LINK_MODE`
> 即退回复制（多占约 5-7 GB）。

> 默认情况下 `setup.ps1` 会在仓库的上一级创建/复用 `IrisFlow-sidecars`；设置 `SIDECAR_HOME` 可改到其他盘。
> Python 3.10 解释器、wheel 缓存、模型权重和 venv 都在 `SIDECAR_HOME` 下；setup 不会把模型装进系统 Python 或仓库目录。

换盘或换目录时用环境变量覆盖（**setup、serve、start_sidecars 要使用同一个值**）：

```powershell
#例如
$env:SIDECAR_HOME = "D:\models\IrisFlow-sidecars"
```

> 两个 venv 的 torch 版本不同（2.9.1 / 2.7.1），无法硬链接共享，各占一份 CUDA 运行库。
> 零安装方案（edge-tts 旁白 + 上传 BGM）仍然可用，不占额外磁盘。

## 下载 / 安装位置（setup.ps1）

| 内容 | 默认位置 | 说明 |
|---|---|---|
| Python 3.10.11 安装包 | `<SIDECAR_HOME>\python-3.10.11-amd64.exe` | 下载后静默安装到 `<SIDECAR_HOME>\python310`；安装完可删安装包 |
| uv wheel 缓存 | `<SIDECAR_HOME>\.uv-cache` | `UV_CACHE_DIR`；两个 venv 共享 |
| CosyVoice venv | `<SIDECAR_HOME>\cosyvoice\.venv` | setup 创建；启动器使用其中的 `Scripts\python.exe` |
| CosyVoice 源码 | `<SIDECAR_HOME>\cosyvoice\repo` | `git clone` Gitee 镜像；`COSYVOICE_REPO` 可覆盖 |
| CosyVoice 权重 | `<SIDECAR_HOME>\cosyvoice\models\CosyVoice2-0.5B` | ModelScope `iic/CosyVoice2-0.5B` |
| CosyVoice 提示音色 | `<SIDECAR_HOME>\cosyvoice\voices` | setup 从 `repo\asset\zero_shot_prompt.wav` 复制为 `default.wav`；也可放 3–10s 自定义 wav |
| Stable Audio venv | `<SIDECAR_HOME>\stable-audio\.venv` | setup 创建 |
| Stable Audio 权重 | `<SIDECAR_HOME>\stable-audio\models\stable-audio-open-small` | 有 `HF_TOKEN` 时走 HuggingFace（只下 `model.safetensors` / `model_config.json` 等），否则走 ModelScope |

> setup / serve / start_sidecars 脚本本身在 `<repo>\deploy\...`，不随模型下载；模型文件和 venv 都不进仓库。

## 启动路径要求

**启动器 `start_sidecars.py` 只按固定布局找 venv 和 serve.py**：

| 启动对象 | 必需路径 |
|---|---|
| CosyVoice | `<SIDECAR_HOME>\cosyvoice\.venv\Scripts\python.exe` + `<repo>\deploy\cosyvoice\serve.py` |
| Stable Audio | `<SIDECAR_HOME>\stable-audio\.venv\Scripts\python.exe` + `<repo>\deploy\stable-audio\serve.py` |

- 启动器默认 `SIDECAR_HOME = <repo 上一级>\IrisFlow-sidecars`；安装到别处时，启动前设置 `$env:SIDECAR_HOME = "<实际路径>"`。启动器会把它和端口传给子进程。
- 目录名 `cosyvoice` / `stable-audio` 及各自 `.venv` 不要随意改名；启动器没有单独的 venv 路径参数。
- 手动 `serve.ps1` 同样从 `SIDECAR_HOME` 下的 venv 启动 `serve.py`；默认值按脚本自身位置推算，换盘后要设 `SIDECAR_HOME`。

**`serve.py` 的模型/音色路径**：

| Sidecar | 内容 | 默认路径 | 覆盖变量 |
|---|---|---|---|
| CosyVoice | 权重 | `<SIDECAR_HOME>\cosyvoice\models\CosyVoice2-0.5B` | `COSYVOICE_MODEL_DIR` |
| CosyVoice | 提示音色 | `<SIDECAR_HOME>\cosyvoice\voices` | `COSYVOICE_VOICES_DIR` |
| CosyVoice | 源码 | `<SIDECAR_HOME>\cosyvoice\repo` | `COSYVOICE_REPO_DIR` |
| CosyVoice | 端口 | 9701 | `COSYVOICE_PORT` |
| Stable Audio | 权重 | `<SIDECAR_HOME>\stable-audio\models\stable-audio-open-small` | `STABLE_AUDIO_MODEL_DIR` |
| Stable Audio | 端口 | 9702 | `STABLE_AUDIO_PORT` |

- 端口必须和 `backend/data/composer_config.json` 的 `tts.base_url` / `music.base_url` 一致（默认 9701/9702）；改端口时两边都改，否则后端会显示 `reachable: false`。
- 只移动权重或音色、保留 venv 时，设置对应 `COSYVOICE_*` / `STABLE_AUDIO_*` 环境变量即可；启动器会继承这些变量。
- `/health` 只验证 HTTP 服务，不加载模型，也不检查权重/音色目录。路径不对时服务仍可能显示 healthy，但第一次 TTS/BGM 请求会报错；错误会写入 `logs/sidecars/*.log`，可通过 `GET /api/composer/sidecars` 查看。

**常见路径错误**：

| 现象 | 原因 | 处理 |
|---|---|---|
| 启动器提示 `venv Python 不存在` | `SIDECAR_HOME` 不对或未安装 | 设对 `SIDECAR_HOME`，或重新运行对应的 `setup.ps1` |
| CosyVoice 请求返回 `缺少提示音色: ...voices\default.wav` | voices 目录/文件缺失 | 放入 3–10s wav 到 `<SIDECAR_HOME>\cosyvoice\voices\default.wav`，或对应音色名 |
| `No module named 'cosyvoice'` | repo 目录缺失或路径不对 | 重新 setup，或设 `COSYVOICE_REPO_DIR` |
| CosyVoice 模型加载失败 | 权重目录不对 | 设 `COSYVOICE_MODEL_DIR`，或重新 setup |
| Stable Audio 报 `model_config.json` 不存在 | 权重目录不对 | 设 `STABLE_AUDIO_MODEL_DIR`，或重新 setup |
| 端口已被占用 | 已有一个 sidecar 或其他进程 | 停止重复进程，或改端口并同步后端 base_url |
| 后端 `reachable: false` | 服务未启动/端口或 base_url 不一致 | 查 `/health`、日志与 `composer_config.json` |

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

> **CosyVoice 依赖兼容性**（Windows + RTX 50 系兼容性结论）：
> - 仓库自带 `requirements.txt` 固定 `torch==2.3.1`（cu121），不支持 Blackwell → 改用裁剪清单，
>   锁定 `torch==2.9.1+cu128`（SJTU 索引，`--no-deps` 安装，纯 Python 依赖单独装）
> - `matcha-tts` 的 Cython 扩展需要 MSVC Build Tools，但该扩展仅训练用 → setup 把 matcha
>   源码内置到 venv 并打补丁（清空 `utils/__init__`、替换 `pylogger` 的 lightning 依赖）
> - `openai-whisper` 用 20250625（旧版 20231117 构建失败），走 PyPI
> - `pyworld`（训练）、`deepspeed`/`tensorrt`（Linux）、`gradio`/`tensorboard`/`lightning`（训练/演示）已排除
>
> **Stable Audio 兼容性**（Windows + RTX 50 系兼容性）：
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

| 项 | 说明 |
|---|---|
| uv | 安装依赖（uv pip + 硬链接去重） |
| 宿主机 Python | 3.10 由脚本从华为镜像下载安装包静默安装到 `<SIDECAR_HOME>\python310`，无需预装 |
| 国内 CPython 镜像 | 华为云 `mirrors.huaweicloud.com/python/`（Gitee/GitHub 的 standalone 构建不可达） |
| NVIDIA 驱动 | RTX 50 系（Blackwell）需 **CUDA 12.8+ 的 torch 轮子** |
| 磁盘 | 预留约 20 GB（两个 venv + 权重） |

> **RTX 50 系注意**：Blackwell（sm_120）只能用 `cu128` 及以上的 torch（≥ 2.7）。
> `setup.ps1` 已默认 `CUDA_TAG=cu128`；老显卡可 `$env:CUDA_TAG="cu124"`。
>
> **Stable Audio 模型下载**：先到 <https://huggingface.co/stabilityai/stable-audio-open-small>
> 接受许可，然后 `$env:HF_TOKEN="hf_..."` 再运行 setup。

## 部署步骤（Windows PowerShell）

```powershell
# 1. 语音（需要 NVIDIA GPU + CUDA；8–12 GB 显存可跑 CosyVoice2-0.5B）
cd deploy\cosyvoice
.\setup.ps1

# 2. 背景音乐（CPU 可跑，341M 模型）
cd ..\stable-audio
.\setup.ps1
```

首次运行会下载数 GB 权重，耗时较长。`setup.ps1` 只做一次性安装；启动服务（推荐一键启动两个，
在仓库根目录执行）：

```powershell
python deploy\start_sidecars.py
# 或者从 backend 目录使用 uv：
# cd backend; uv run python ..\deploy\start_sidecars.py
```

- 同时拉起 CosyVoice（9701）和 Stable Audio（9702），等待 `/health` 就绪
- 日志固定写到 `logs/sidecars/cosyvoice.log` / `logs/sidecars/stable-audio.log`
- 模型仍是懒加载：`/health` 就绪只代表 HTTP 服务已启动，第一次 TTS/BGM 请求才加载权重
- 已健康运行的 sidecar 会被复用；某个退出时启动器继续照看另一个；Ctrl+C 统一停止（`taskkill /T`）
- 启动器只负责 sidecar，后端仍按原来的命令单独启动

手动启动（两个终端）仍然可用，但不会写入上面的日志文件：

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

## 后端读取健康与日志

后端不管理 sidecar 进程，只提供只读快照：

```powershell
curl "http://localhost:8000/api/composer/sidecars?lines=200"
```

返回两个 sidecar 的：

- `reachable` / `model_ok`：`/health` 连通且模型名匹配
- `health`：sidecar 的 `/health` JSON
- `log_path`：日志文件路径
- `log_tail`：最近 N 行日志（`lines` 默认 120，上限 500）

健康探测优先使用 composer 配置里的本地 `tts.base_url` / `music.base_url`；配置成云端时回退到
默认本地端口 9701/9702。日志来自一键启动器；用 `serve.ps1` 手动启动时该文件可能为空。

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
8 GB 显存属于踩线配置，可能需要量化或降档。

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
