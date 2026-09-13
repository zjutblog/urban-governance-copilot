# 启动本地微调模型推理服务（scripts/serve_local_llm.py），供 LLM_MODE=local 使用。
# 用法：在项目根目录执行  .\start_local_model.ps1
$ErrorActionPreference = "Stop"
$py = "D:\anacanda\envs\urban_agent\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

# 从 .env 字节安全读取 LOCAL_MODEL_DIR / 端口（.env 是 GBK 注释，需按字节解析）
$envPath = Join-Path $PSScriptRoot ".env"
$lines = [System.IO.File]::ReadAllBytes($envPath)
$txt = [System.Text.Encoding]::GetEncoding(0).GetString($lines)  # 系统 ANSI 兜底
$modelDir = ""
$baseUrl = ""
foreach ($ln in $txt -split "`r?`n") {
    if ($ln -match '^\s*LOCAL_MODEL_DIR\s*=\s*(.+)\s*$') { $modelDir = $matches[1].Trim() }
    if ($ln -match '^\s*LOCAL_BASE_URL\s*=\s*(.+)\s*$')   { $baseUrl = $matches[1].Trim() }
}
if (-not $modelDir) { $modelDir = Join-Path $PSScriptRoot "data\models\qwen3-ugov" }
$port = 8011
if ($baseUrl -match ':(\d+)/') { $port = [int]$matches[1] }

Write-Host "启动本地模型: $modelDir  on port $port"
if (-not (Test-Path $modelDir)) { Write-Host "未找到模型目录: $modelDir"; exit 1 }
& $py (Join-Path $PSScriptRoot "scripts\serve_local_llm.py") --model $modelDir --port $port
