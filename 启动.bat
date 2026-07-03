@echo off
cd /d "%~dp0"
echo [启动] 打开管理界面，在网页里控制任务...
if exist "dist\京东外卖领券工具.exe" (
    dist\京东外卖领券工具.exe
) else (
    python main.py
)
pause
