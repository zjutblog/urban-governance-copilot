@echo off
REM run.bat —— 用 urban_agent 环境运行 main.py（cmd 版）
REM 用法：run.bat "留言内容"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
"D:\anacanda\envs\urban_agent\python.exe" "%~dp0main.py" %*
