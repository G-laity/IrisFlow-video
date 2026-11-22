# Stable Audio Open Small sidecar 一次性安装（国内源版）
# 用法: .\setup.ps1   （可选 $env:SIDECAR_HOME / $env:CUDA_TAG / $env:HF_TOKEN 覆盖）
$ErrorActionPreference = "Stop"

$SidecarHome = if ($env:SIDECAR_HOME) { $env:SIDECAR_HOME } else {
    Join-Path (Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent) "IrisFlow-sidecars"
}
$Root = Join-Path $SidecarHome "stable-audio"
$Venv = Join-Path $Root ".venv"
$Models = Join-Path $Root "models"

Write-Host "SIDECAR_HOME = $SidecarHome"
New-Item -ItemType Directory -Force -Path $Root, $Models | Out-Null

# ── 国内源 ───────────────────────────────────────
$PyPiIndex  = if ($env:PYPI_INDEX_URL)  { $env:PYPI_INDEX_URL }  else { "https://pypi.tuna.tsinghua.edu.cn/simple" }
$TorchIndex = if ($env:TORCH_INDEX_URL) { $env:TORCH_INDEX_URL } else { "https://mirror.sjtu.edu.cn/pytorch-wheels" }
$Py310Url   = if ($env:PYTHON310_URL)   { $env:PYTHON310_URL }   else { "https://mirrors.huaweicloud.com/python/3.10.11/python-3.10.11-amd64.exe" }
$env:PIP_INDEX_URL = $PyPiIndex
$env:UV_DEFAULT_INDEX = $PyPiIndex
$env:UV_INDEX_URL = $PyPiIndex
$env:UV_HTTP_TIMEOUT = "180"
if (-not $env:HF_ENDPOINT) { $env:HF_ENDPOINT = "https://hf-mirror.com" }
# hf-mirror 与新版 huggingface_hub 的 xet 传输不兼容（会跳转 huggingface.co），禁用 xet
$env:HF_HUB_DISABLE_XET = "1"

# ── uv 缓存 + 硬链接（与 cosyvoice 共享同一份缓存）──
$Uv = Get-Command uv -ErrorAction SilentlyContinue
if ($Uv) {
    $env:UV_CACHE_DIR = Join-Path $SidecarHome ".uv-cache"
    $env:UV_LINK_MODE = "hardlink"
}

# 1. Python 3.10 venv（与 cosyvoice 相同的获取逻辑）
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

function Install-Pkgs {
    if ($Uv) {
        uv pip install --python $Python @args
    } else {
        & $Pip install @args
    }
    if ($LASTEXITCODE -ne 0) { throw "依赖安装失败（见上方输出）" }
}

# 2. stable-audio-tools（Stability AI 官方推理库）
Install-Pkgs stable-audio-tools
Install-Pkgs -r (Join-Path $PSScriptRoot "requirements.txt")

# 3. torch（在 stable-audio-tools 之后安装：其依赖会把 torch 降级为 CPU 版）
$CudaTag = if ($env:CUDA_TAG) { $env:CUDA_TAG } else { "cpu" }
$TorchUrl = "$TorchIndex/$CudaTag"
Write-Host "安装 torch ($CudaTag) ← $TorchUrl"
if (-not $Uv) { & $Pip install --upgrade pip -i $PyPiIndex }
# 先装 torch 的纯 Python 依赖（PyPI），再锁定 cu128/cpu 版本从专用索引安装，
# 避免 --extra-index-url 让解析器选中 PyPI 上的非 CUDA 构建。
Install-Pkgs sympy networkx filelock jinja2 fsspec typing-extensions mpmath setuptools
$TorchVersion = if ($env:TORCH_VERSION) { $env:TORCH_VERSION } else { "2.7.1" }
$TorchVisionVersion = if ($env:TORCHVISION_VERSION) { $env:TORCHVISION_VERSION } else { "0.22.1" }
if ($CudaTag -eq "cpu") {
    # Windows 的 PyPI torch 即 CPU 构建
    Install-Pkgs "torch==$TorchVersion" "torchaudio==$TorchVersion" "torchvision==$TorchVisionVersion"
} else {
    # SJTU 镜像的 /cuXXX/ 是扁平 wheel 目录，直接按 URL 安装
    $PyTag = "cp310-cp310-win_amd64"
    $TorchWheel = "$TorchUrl/torch-$TorchVersion%2B$CudaTag-$PyTag.whl"
    $AudioWheel = "$TorchUrl/torchaudio-$TorchVersion%2B$CudaTag-$PyTag.whl"
    $VisionWheel = "$TorchUrl/torchvision-$TorchVisionVersion%2B$CudaTag-$PyTag.whl"
    Install-Pkgs $TorchWheel $AudioWheel $VisionWheel --no-deps
}

# 4. 模型权重：设置 HF_TOKEN 时走 HuggingFace（镜像），否则走 ModelScope
#    HF_TOKEN 可来自环境变量，或 backend\data\secrets.json（设置面板「密钥」标签页，已 gitignore）
if (-not $env:HF_TOKEN) {
    $SecretsFile = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "backend\data\secrets.json"
    if (Test-Path $SecretsFile) {
        try {
            $Secrets = Get-Content $SecretsFile -Raw | ConvertFrom-Json
            if ($Secrets.HF_TOKEN) { $env:HF_TOKEN = [string]$Secrets.HF_TOKEN }
        } catch { }
    }
}
#    只下载 model.safetensors + 配置，避免仓库里的 base_model.ckpt / model.ckpt（各 1.6GB）
if ($env:HF_TOKEN) {
    Write-Host "下载 stable-audio-open-small ← HuggingFace（HF_ENDPOINT=$env:HF_ENDPOINT）..."
    & $Python -c @"
from huggingface_hub import snapshot_download
snapshot_download(
    'stabilityai/stable-audio-open-small',
    local_dir=r'$Models\stable-audio-open-small',
    allow_patterns=['model.safetensors', 'model_config.json', 'LICENSE', 'README.md'],
)
"@
} else {
    Write-Host "未设置 HF_TOKEN，改用 ModelScope 镜像下载 ..."
    & $Python -c @"
from modelscope import snapshot_download
snapshot_download('stabilityai/stable-audio-open-small', local_dir=r'$Models\stable-audio-open-small')
"@
}
if ($LASTEXITCODE -ne 0) { throw "stable-audio-open-small 权重下载失败" }

Write-Host ""
Write-Host "安装完成（模型权重缺失时见上方警告）。启动服务: .\serve.ps1"
Write-Host "后端配置 music.base_url = http://127.0.0.1:9702/v1"
