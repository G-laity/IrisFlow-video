# CosyVoice 2.5 sidecar 一次性安装（国内源版）
# 用法: .\setup.ps1   （可选 $env:SIDECAR_HOME / $env:CUDA_TAG / $env:COSYVOICE_REPO 覆盖）
$ErrorActionPreference = "Stop"

$SidecarHome = if ($env:SIDECAR_HOME) { $env:SIDECAR_HOME } else {
    Join-Path (Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent) "IrisFlow-sidecars"
}
$Root = Join-Path $SidecarHome "cosyvoice"
$Venv = Join-Path $Root ".venv"
$Repo = Join-Path $Root "repo"
$Models = Join-Path $Root "models"
$Voices = Join-Path $Root "voices"

Write-Host "SIDECAR_HOME = $SidecarHome"
New-Item -ItemType Directory -Force -Path $Root, $Models, $Voices | Out-Null

# ── 国内源 ───────────────────────────────────────
$PyPiIndex  = if ($env:PYPI_INDEX_URL)  { $env:PYPI_INDEX_URL }  else { "https://pypi.tuna.tsinghua.edu.cn/simple" }
$TorchIndex = if ($env:TORCH_INDEX_URL) { $env:TORCH_INDEX_URL } else { "https://mirror.sjtu.edu.cn/pytorch-wheels" }
$Py310Url   = if ($env:PYTHON310_URL)   { $env:PYTHON310_URL }   else { "https://mirrors.huaweicloud.com/python/3.10.11/python-3.10.11-amd64.exe" }
$env:PIP_INDEX_URL = $PyPiIndex
$env:UV_DEFAULT_INDEX = $PyPiIndex
$env:UV_INDEX_URL = $PyPiIndex
$env:UV_HTTP_TIMEOUT = "180"

# ── uv 缓存 + 硬链接 ─────────────────────────────
$Uv = Get-Command uv -ErrorAction SilentlyContinue
if ($Uv) {
    $env:UV_CACHE_DIR = Join-Path $SidecarHome ".uv-cache"
    $env:UV_LINK_MODE = "hardlink"
}

# 1. Python 3.10 venv（CosyVoice 锁定 3.10）
#    顺序：venv 已存在 → 跳过；本地 python310 → 用；py -3.10 → 用；
#    否则从国内镜像下载 CPython 3.10.11 安装包静默安装到 <SIDECAR_HOME>\python310
$Py310 = Join-Path $SidecarHome "python310\python.exe"
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    $BasePy = $null
    if ($env:PYTHON310 -and (Test-Path $env:PYTHON310)) {
        $BasePy = $env:PYTHON310
    } elseif (Test-Path $Py310) {
        $BasePy = $Py310
    }
    if (-not $BasePy) {
        $Installer = Join-Path $SidecarHome "python-3.10.11-amd64.exe"
        if (-not (Test-Path $Installer)) {
            Write-Host "下载 Python 3.10.11 ← $Py310Url"
            Invoke-WebRequest -Uri $Py310Url -OutFile $Installer
        }
        $Py310Dir = Split-Path $Py310 -Parent
        Write-Host "静默安装 Python 3.10.11 → $Py310Dir"
        Start-Process -FilePath $Installer -Wait -ArgumentList @(
            "/quiet", "InstallAllUsers=0", "TargetDir=`"$Py310Dir`"",
            "Include_pip=1", "Include_launcher=0", "PrependPath=0", "Shortcuts=0", "Include_test=0"
        )
        if (-not (Test-Path $Py310)) { throw "Python 3.10 安装失败: $Py310 不存在" }
        $BasePy = $Py310
    }
    & $BasePy -m venv $Venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
        throw "创建 venv 失败"
    }
}
$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

# 安装器：优先 uv pip（硬链接去重），否则退回 pip
function Install-Pkgs {
    if ($Uv) {
        uv pip install --python $Python @args
    } else {
        & $Pip install @args
    }
    if ($LASTEXITCODE -ne 0) { throw "依赖安装失败（见上方输出）" }
}

# 2. torch（RTX 50 系必须 cu128 / torch >= 2.7；老卡可用 cu124）
$CudaTag = if ($env:CUDA_TAG) { $env:CUDA_TAG } else { "cu128" }
$TorchUrl = "$TorchIndex/$CudaTag"
Write-Host "安装 torch ($CudaTag) ← $TorchUrl"
if (-not $Uv) { & $Pip install --upgrade pip -i $PyPiIndex }
# 先装 torch 的纯 Python 依赖（PyPI），再锁定 cu128/cpu 版本从专用索引安装，
# 避免 --extra-index-url 让解析器选中 PyPI 上的非 CUDA 构建。
Install-Pkgs sympy networkx filelock jinja2 fsspec typing-extensions mpmath setuptools
$TorchVersion = if ($env:TORCH_VERSION) { $env:TORCH_VERSION } else { "2.9.1" }
if ($CudaTag -eq "cpu") {
    # Windows 的 PyPI torch 即 CPU 构建
    Install-Pkgs "torch==$TorchVersion" "torchaudio==$TorchVersion"
} else {
    # SJTU 镜像的 /cuXXX/ 是扁平 wheel 目录，直接按 URL 安装
    $PyTag = "cp310-cp310-win_amd64"
    $TorchWheel = "$TorchUrl/torch-$TorchVersion%2B$CudaTag-$PyTag.whl"
    $AudioWheel = "$TorchUrl/torchaudio-$TorchVersion%2B$CudaTag-$PyTag.whl"
    Install-Pkgs $TorchWheel $AudioWheel --no-deps
}

# 2.5 内置 matcha 源码（推理只用 components，Cython 扩展仅训练用）
#     pip 安装会触发 MSVC 编译（本机无 Build Tools），改为复制源码到 site-packages，
#     并移除 utils/__init__ 的 hydra/lightning 污染与 pylogger 的 lightning 依赖。
$SitePackages = Join-Path $Venv "Lib\site-packages"
if (-not (Test-Path (Join-Path $SitePackages "matcha"))) {
    Write-Host "内置 matcha 源码（绕过 Cython 编译）..."
    & $Python (Join-Path $PSScriptRoot "vendor_matcha.py") $SitePackages
    if ($LASTEXITCODE -ne 0) { throw "内置 matcha 失败" }
}

# 3. CosyVoice 源码 + 推理依赖
#    源码默认走 Gitee 镜像（GitHub 直连在国内通常不可用）；
#    仓库 requirements.txt 固定 torch==2.3.1（cu121，不支持 RTX 50），故使用裁剪版依赖清单，
#    matcha-tts / openai-whisper 走 PyPI，无需 GitHub 子模块。
if (-not (Test-Path $Repo)) {
    $RepoUrl = if ($env:COSYVOICE_REPO) { $env:COSYVOICE_REPO } else { "https://gitee.com/mirrors/CosyVoice.git" }
    git clone --depth 1 $RepoUrl $Repo
    if ($LASTEXITCODE -ne 0) { throw "克隆 CosyVoice 失败（可设 COSYVOICE_REPO 为其他镜像地址）" }
}
& $Python (Join-Path $PSScriptRoot "patch_repo.py") $Repo
if ($LASTEXITCODE -ne 0) { throw "CosyVoice 源码补丁失败" }
Install-Pkgs -r (Join-Path $PSScriptRoot "requirements.txt")

# 4. 模型权重（ModelScope，国内直连）
Write-Host "下载 CosyVoice2-0.5B ..."
& $Python -c @"
from modelscope import snapshot_download
snapshot_download('iic/CosyVoice2-0.5B', local_dir=r'$Models\CosyVoice2-0.5B')
"@
if ($LASTEXITCODE -ne 0) { throw "CosyVoice2-0.5B 权重下载失败" }

# 5. 默认提示音色（复制仓库自带示例音色，缺失时）
$DefaultVoice = Join-Path $Voices "default.wav"
if (-not (Test-Path $DefaultVoice)) {
    $Sample = Join-Path $Repo "asset\zero_shot_prompt.wav"
    if (Test-Path $Sample) {
        Copy-Item $Sample $DefaultVoice
        Write-Host "已复制默认提示音色: $DefaultVoice"
    }
}

Write-Host ""
Write-Host "安装完成。"
Write-Host "  1) 将 3-10 秒提示音色 wav 放入: $Voices\default.wav（或按音色名命名）"
Write-Host "  2) 启动服务: .\serve.ps1"
Write-Host "  3) 后端配置 tts.base_url = http://127.0.0.1:9701/v1"
