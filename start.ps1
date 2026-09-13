# start.ps1 —— 用 urban_agent 环境启动 FastAPI 服务（Web 界面）
# 用法：
#   .\start.ps1
# 浏览器打开 http://127.0.0.1:8000
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = "D:\anacanda\envs\urban_agent\python.exe"

if (-not (Test-Path $py)) {
    Write-Error "找不到 urban_agent 环境的 Python：$py"
    exit 1
}

# 终端 UTF-8 输出，避免中文乱码
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 启动前自动杀掉占用 8000 的旧进程，避免"旧进程没停、新进程起不来"
$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($conns) {
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid in $pids) {
        if ($pid -and $pid -ne $PID) {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "[start] 已停止占用 8000 端口的旧进程 (PID $pid)"
        }
    }
    Start-Sleep -Seconds 1
}

Push-Location $root
& $py -m uvicorn server:app --host 127.0.0.1 --port 8000
$code = $LASTEXITCODE
Pop-Location
exit $code
