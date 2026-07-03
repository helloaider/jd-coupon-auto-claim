@echo off
cd /d "%~dp0"
echo [直接领券] 启动浏览器 + 调度器，不开管理界面...
python worker.py
pause
