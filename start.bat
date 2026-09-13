@echo off
REM start.bat —— 用 urban_agent 环境启动 Web 服务（cmd 版）
REM 启动后浏览器打开 http://127.0.0.1:8000
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
"D:\anacanda\envs\urban_agent\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000
