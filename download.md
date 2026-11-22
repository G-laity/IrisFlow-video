# IrisFlow 依赖下载清单

> 用途：视频合成器（IRIS VIDEO COMPOSER）M2/M4 的本地模型环境。
> **两个 sidecar 均按 GPU（NVIDIA RTX 5060 Laptop 8 GB，驱动 576.65）配置。**
> 本文件只负责「下载什么、去哪里下载、什么版本」；安装与启动步骤见 [`deploy/README.md`](./deploy/README.md)。
>
> 更新时间：2026-11-22 · 对应版本：IrisFlow 0.35.0

---

## 一、本机已具备（无需下载）

| 工具 | 本机版本 | 说明 |
|---|---|---|
| Python（后端） | 3.13 / 3.14（uv 管理） | 后端运行环境 |
| uv | 0.11.26 | 用于创建 sidecar 的 Python 3.10 venv |
| Node.js | v24.18.0 | 前端构建 |
| pnpm | 11.9.0 | 前端包管理 |
| git | 已装 | 克隆 CosyVoice 源码 |
| ffmpeg / ffprobe | 2026-07-09 gyan.dev essentials（PATH：`C:\Users\zhuan\ffmpeg\bin`） | 素材探测 + M3 渲染；M3 所需 libx264 / aac / subtitles / xfade / zoompan / amix / concat 均已验证可用 |
| **edge-tts** | **7.3.1**（后端 venv） | 语音最终兜底，已实测合成成功 |
| NVIDIA 驱动 | 576.65 | 支持 CUDA 12.8，满足 RTX 50 系要求 |

---

## 二、需要下载的东西（两个 sidecar 均 GPU）

### 1. Python 3.10（sidecar 专用解释器）

| 项 | 内容 |
|---|---|
| 版本 | **3.10.11**（CosyVoice 官方支持版本；Stable Audio 同用） |
| 下载地址（默认） | https://mirrors.huaweicloud.com/python/3.10.11/python-3.10.11-amd64.exe |
| 备用镜像 | https://mirrors.aliyun.com/python-release/windows/ · https://registry.npmmirror.com/-/binary/python/3.10.11/ |
| 安装方式 | setup.ps1 自动下载并静默安装（`/quiet InstallAllUsers=0 TargetDir=...`） |
| 大小 | 下载约 28 MB / 安装后约 100 MB |
| 落盘 | `E:\NT\IrisFlow-sidecars\python310\` |
| 覆盖变量 | `PYTHON310`（已装好的 python.exe 路径）/ `PYTHON310_URL`（安装包地址） |

> uv 的 python-build-standalone 走 GitHub，国内不可达（南大/清华/中科大镜像均未覆盖该资产），
> 因此改用国内 CPython 官方安装包。GitHub 直连在本机实测返回 000。

### 2. PyTorch + TorchAudio（cu128，GPU 版）

| 项 | 内容 |
|---|---|
| 版本 | **torch ≥ 2.7**，torchaudio 与 torch **同版本** |
| 说明 | RTX 50 系（Blackwell，sm_120）**必须使用 cu128 及以上**的轮子；cu124 不可用 |
| 官方向导 | https://pytorch.org/get-started/locally/ |
| wheel 索引（官方） | https://download.pytorch.org/whl/cu128 |
| **国内镜像（默认使用）** | https://mirror.sjtu.edu.cn/pytorch-wheels/cu128 |
| 直链示例（cp310/win） | `.../cu128/torch-2.9.1%2Bcu128-cp310-cp310-win_amd64.whl` |
| 安装方式 | 镜像的 `/cu128/` 是**扁平 wheel 目录**（非 PEP 503 索引），uv 无法解析版本 → setup 脚本按 whl 直链 `--no-deps` 安装 |
| 下载量 / 落盘 | 约 1.5-2 GB 下载 / **5-7 GB 安装后**（含 `nvidia-*` CUDA 运行库） |
| 落盘 | 两个 sidecar 各自的 `.venv`（**会装两份，约 10-14 GB**） |

> 想省 5-7 GB 可以让 Stable Audio 用 CPU 版 torch（`CUDA_TAG=cpu`），代价是 11 秒 BGM 生成从 ~15 秒变成 1-3 分钟。本文按你的要求两个都 GPU。

### 3. CosyVoice 源码

| 项 | 内容 |
|---|---|
| 版本 | `main` 分支（跟随官方最新，镜像同步） |
| 地址（默认，国内） | **https://gitee.com/mirrors/CosyVoice** |
| 官方地址（备用） | https://github.com/FunAudioLLM/CosyVoice |
| 克隆命令 | `git clone --depth 1 https://gitee.com/mirrors/CosyVoice.git` |
| 子模块 | **不需要**：`matcha-tts` 改用 PyPI 包（GitHub 子模块国内不可达） |
| 大小 | 约 5-10 MB（`--depth 1`） |
| 落盘 | `E:\NT\IrisFlow-sidecars\cosyvoice\repo\` |
| 覆盖变量 | `COSYVOICE_REPO`（其他镜像/代理 git 地址） |

> ⚠️ **依赖兼容性**：仓库自带 `requirements.txt` 固定 `torch==2.3.1`（cu121），
> 不支持 RTX 50 系（sm_120）。安装改用裁剪版清单 `deploy/cosyvoice/requirements.txt`：
> 保留 `torch≥2.7 + cu128`，排除 `pyworld`（训练）、`deepspeed`/`tensorrt`（Linux）、
> `gradio`/`tensorboard`/`lightning`（训练/演示）等，`matcha-tts` / `openai-whisper` 走 PyPI。

### 4. CosyVoice2-0.5B 模型权重

| 项 | 内容 |
|---|---|
| 版本 | **CosyVoice2-0.5B**（语音合成主模型） |
| 下载地址（国内推荐） | https://modelscope.cn/models/iic/CosyVoice2-0.5B |
| 下载地址（备用） | https://huggingface.co/FunAudioLLM/CosyVoice2-0.5B |
| 源码镜像 | 默认 GitHub；可用 `COSYVOICE_REPO` 指定代理地址 |
| 下载命令 | `snapshot_download('iic/CosyVoice2-0.5B', local_dir='...\\models\\CosyVoice2-0.5B')`（setup.ps1 已含） |
| 大小 | 实测 **5.3 GB**（仓库含 llm.pt / flow.pt 等多个 checkpoint，21 个文件） |
| 落盘 | `E:\NT\IrisFlow-sidecars\cosyvoice\models\CosyVoice2-0.5B\` |
| 额外需要 | **3-10 秒提示音色 wav**（自行录制或截取干净人声），放 `...\cosyvoice\voices\default.wav` |

### 5. Stable Audio 推理库（stable-audio-tools）

| 项 | 内容 |
|---|---|
| 版本 | **PyPI 最新稳定版**（未固定版本号，跟随官方） |
| PyPI | `pip install stable-audio-tools` |
| 源码 | https://github.com/Stability-AI/stable-audio-tools |
| 大小 | 源码 + 依赖约几十 MB（torch 除外） |
| 落盘 | `E:\NT\IrisFlow-sidecars\stable-audio\.venv\` |

### 6. Stable Audio Open Small 模型权重

| 项 | 内容 |
|---|---|
| 版本 | **stable-audio-open-small（341M 参数）** |
| 下载地址（默认） | **ModelScope 官方镜像**：https://modelscope.cn/models/stabilityai/stable-audio-open-small |
| 下载方式 | `snapshot_download('stabilityai/stable-audio-open-small', local_dir='...')`（setup.ps1 已含），**匿名可下，无需 token** |
| 大小 | 约 1.6 GB（model.safetensors） |
| 落盘 | `E:\NT\IrisFlow-sidecars\stable-audio\models\stable-audio-open-small\` |
| 备用（HF） | https://huggingface.co/stabilityai/stable-audio-open-small（**gated**，需账号接受许可 + `HF_TOKEN`） |

> HF 原仓库为门禁模型，匿名请求返回 403 "not in the authorized list"。已实测 ModelScope
> 官方镜像可匿名完整下载（文件列表与 HF 一致），因此安装流程不需要 HF token。

### 7. 其他 Python 依赖（setup.ps1 自动安装）

| 包 | 版本约束 | 用途 |
|---|---|---|
| fastapi | ≥ 0.115 | sidecar HTTP 服务 |
| uvicorn | ≥ 0.30 | sidecar 运行 |
| modelscope | ≥ 1.18 | CosyVoice 权重下载 |
| soundfile | ≥ 0.12 | 音频读写 |
| numpy | < 2.0 | CosyVoice 兼容性 |

---

## 三、可选（M4 主题曲，非必需）

| 项 | 内容 |
|---|---|
| ACE-Step 源码 | https://github.com/ace-step/ACE-Step |
| ACE-Step 权重（3.5B） | https://huggingface.co/ACE-Step/ACE-Step-v1-3.5B |
| 显存要求 | 8-12 GB（RTX 5060 的 8 GB 属于踩线，可能需量化） |
| 磁盘 | ≈ 10 GB（权重 ~7 GB + venv） |
| 结论 | M4 再评估，不影响 M2/M3 |

---

## 四、磁盘占用汇总（两个都 GPU）

**实测值（2026-11-22 安装完成后）**：

| 组件 | 实测磁盘 |
|---|---|
| `python310\`（CPython 3.10.11） | ~0.1 GB |
| `cosyvoice\.venv`（torch 2.9.1+cu128） | **5.1 GB** |
| `cosyvoice\models\CosyVoice2-0.5B`（含全部 checkpoint） | **5.3 GB** |
| `cosyvoice\repo`（Gitee 浅克隆） | ~0.05 GB |
| `stable-audio\.venv`（torch 2.7.1+cu128 + stable-audio-tools） | **5.7 GB** |
| `stable-audio\models\stable-audio-open-small` | **1.6 GB** |
| `.uv-cache` + 其他 | ~2.3 GB |
| **合计** | **≈ 20 GB** |

> 比早期估算（10-12 GB）大，原因：CosyVoice2-0.5B 仓库实际包含 5.3 GB 的多个 checkpoint；
> 两个 venv 各装一份 CUDA 运行库（硬链接只在同版本 wheel 间生效，torch 2.7/2.9 版本不同无法共享）。

**下载/存储去重机制**（`setup.ps1` 已内置）：

- `UV_CACHE_DIR = <SIDECAR_HOME>\.uv-cache` —— 两个 sidecar 共用同一份 wheel 缓存，
  同版本 torch / 依赖只下载一次
- `UV_LINK_MODE = hardlink` —— 安装时从缓存硬链接到各自 venv（缓存与 venv 同盘），
  两个 venv 的 torch 指向同一份物理文件，磁盘只占一份
- 若 SIDECAR_HOME 所在盘不支持硬链接（非 NTFS），去掉 `UV_LINK_MODE` 即退回复制，
  总占用回到约 13-17 GB

所在盘：`E:`（当前剩余约 170 GB，充足）。

---

## 五、目录结构（安装后）

```
E:\NT\IrisFlow-video\deploy\        # 脚本（git 管理）
├── cosyvoice\                      # setup.ps1 / serve.ps1 / serve.py
└── stable-audio\                   # setup.ps1 / serve.ps1 / serve.py

E:\NT\IrisFlow-sidecars\            # 默认 SIDECAR_HOME（本机私有，勿提交）
├── cosyvoice\
│   ├── .venv\                      # Python 3.10 + torch cu128
│   ├── repo\                       # CosyVoice 源码
│   ├── models\CosyVoice2-0.5B\
│   └── voices\default.wav
└── stable-audio\
    ├── .venv\
    └── models\stable-audio-open-small\
```

改位置：`$env:SIDECAR_HOME = "D:\models\IrisFlow-sidecars"` 后再执行 setup。

---

## 六、下载与安装顺序

```powershell
# 0. 前置变量（可选）
$env:SIDECAR_HOME = "E:\NT\IrisFlow-sidecars"   # 默认值，可省略
$env:HF_TOKEN     = "hf_xxxxxxxx"               # Stable Audio 必需

# 1. 语音（GPU）—— 自动完成：3.10 venv → torch cu128 → 源码 → 权重
cd E:\NT\IrisFlow-video\deploy\cosyvoice
.\setup.ps1

# 2. 音乐（GPU）—— 默认 CPU，必须显式指定 cu128
cd ..\stable-audio
$env:CUDA_TAG = "cu128"
.\setup.ps1
```

---

## 七、安装后验证

```powershell
# 各开一个终端启动
cd E:\NT\IrisFlow-video\deploy\cosyvoice;    .\serve.ps1
cd E:\NT\IrisFlow-video\deploy\stable-audio; .\serve.ps1

# 健康检查
curl http://127.0.0.1:9701/health
# → {"status":"ok","model":"cosyvoice2",...}
curl http://127.0.0.1:9702/health
# → {"status":"ok","model":"stable-audio-open-small",...}

# 后端视角：providers.tts.primary.reachable / providers.music.reachable 应为 true
curl http://localhost:8000/api/composer/config
```

---

## 八、版本策略与常见问题

| 问题 | 处理 |
|---|---|
| RTX 50 系报 "no kernel image is available" | torch 不是 cu128 构建，重装 `--index-url https://download.pytorch.org/whl/cu128` |
| torch 安装时被降级 | 先装 torch，再装 `requirements.txt`（已移除 torch 版本锁定） |
| CosyVoice 在 3.11+ 报 pynini / WeTextProcessing 编译失败 | 必须 3.10（uv 自动处理） |
| Stable Audio 走 HF 时 403 / gated | 默认已改用 ModelScope，无需 token；仅备用 HF 路径需要 |
| HuggingFace 下载慢 | `$env:HF_ENDPOINT = "https://hf-mirror.com"`；CosyVoice 优先用 ModelScope |
| 显存不足（两个服务同开） | 分时启动，或 Stable Audio 改 CPU 版（`CUDA_TAG=cpu`，省约 4 GB 磁盘） |
| 第二个 sidecar 会重新下载 torch 吗 | 不会。共用 `<SIDECAR_HOME>\.uv-cache`，同版本 wheel 命中缓存 |
| 两个 venv 会各存一份 torch 吗 | 默认不会。`UV_LINK_MODE=hardlink` 让两个 venv 指向同一份物理文件；非 NTFS 盘会自动退回复制 |
| setup 脚本在 PowerShell 5.1 下报语法错 | 脚本已保存为 UTF-8 with BOM，请勿另存为无 BOM / ANSI |

> 版本说明：torch / stable-audio-tools / CosyVoice 源码均跟随各自主源的最新稳定版；
> 若新版本出现兼容问题，torch 回退到 `2.7.x`（cu128 索引内仍可获取）。

### 本次安装实际踩到的 Windows 兼容问题（已在脚本中修复）

| 问题 | 处理 |
|---|---|
| `openai-whisper==20231117` 构建失败（缺 pkg_resources） | 升级到 20250625 |
| `matcha-tts` 需要 MSVC 编译 Cython 扩展（仅训练用） | 源码内置到 venv + 补丁（`vendor_matcha.py`） |
| `pyworld` 无 Windows wheel | 源码改为可选导入（`patch_repo.py`） |
| 模型 yaml 预解析 `dataset.processor` → 缺 matplotlib / pyarrow | 两者加入依赖 |
| torchaudio ≥2.9 的 `load()` 强制 torchcodec | `load_wav` 改用 soundfile（`patch_repo.py`） |
| `stable-audio-tools` 依赖把 torch 从 cu128 降级为 CPU | 安装顺序改为：先装 stable-audio-tools，最后用 SJTU 直链覆盖 torch/torchaudio/torchvision（2.7.1/0.22.1+cu128） |
| PyWavelets 1.4.1 与 numpy 2 二进制不兼容 | 升级 PyWavelets ≥1.8 |
| stable-audio-tools LoRA 回调强制导入 pytorch_lightning | 安装 pytorch-lightning |
| 模型采样器为 rf_denoiser，`dpmpp-3m-sde` 不支持 | serve.py 改用 `pingpong` sampler |
| numpy 2 下 `np.random.randint(0, 2**32-1)` 溢出 | serve.py 显式传 seed（<2^31） |
