# run.ps1 —— 用 urban_agent 环境的 Python 直接运行 main.py（无需手动激活环境）
# 用法：
#   .\run.ps1 "小区附近晚上施工噪音很大，希望有关部门处理"
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = "D:\anacanda\envs\urban_agent\python.exe"

if (-not (Test-Path $py)) {
    Write-Error "找不到 urban_agent 环境的 Python：$py"
    exit 1
}

# 终端 UTF-8 输出，避免中文乱码
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Push-Location $root
& $py (Join-Path $root "main.py") @Args
$code = $LASTEXITCODE
Pop-Location
exit $code
