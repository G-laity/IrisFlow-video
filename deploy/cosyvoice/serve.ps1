# 启动 CosyVoice sidecar（http://127.0.0.1:9701）
$ErrorActionPreference = "Stop"
$SidecarHome = if ($env:SIDECAR_HOME) { $env:SIDECAR_HOME } else {
    Join-Path (Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent) "IrisFlow-sidecars"
}
$env:SIDECAR_HOME = $SidecarHome
$Python = Join-Path $SidecarHome "cosyvoice\.venv\Scripts\python.exe"
& $Python (Join-Path $PSScriptRoot "serve.py")
