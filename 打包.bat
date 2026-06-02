@echo off
cd /d "%~dp0"

echo [打包] 自动递增版本号...
python bump_version.py
if errorlevel 1 (
    echo [错误] 版本号递增失败，终止打包
    pause
    exit /b 1
)

echo [打包] 开始打包，请稍候...
taskkill /F /IM "京东外卖抢券工具*" 2>nul
del /F /Q dist\*.exe 2>nul
del /F /Q dist\*.zip 2>nul
rmdir /S /Q build 2>nul

pyinstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo [错误] PyInstaller 打包失败
    pause
    exit /b 1
)

echo.
echo [打包] 清理 dist 目录中的敏感文件...
if exist dist\data rmdir /S /Q dist\data
if exist dist\logs rmdir /S /Q dist\logs
mkdir dist\data
mkdir dist\logs

echo [打包] 更新 dist\config.yaml...
if not exist dist\config.yaml (
    copy /Y config.yaml dist\config.yaml >nul
)
python clean_dist_config.py

echo [打包] 生成发布 zip...
python make_zip.py
if errorlevel 1 (
    echo [错误] zip 生成失败
    pause
    exit /b 1
)

echo.
echo [完成] 打包完成，发布文件在 dist\ 目录下
echo [注意] 首次运行需要确保电脑已安装 Microsoft Edge 浏览器
pause
