@echo off
cd /d "%~dp0"
echo [打包] 自动递增版本号...
python -c "
import re, sys
path = 'src/version.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'__version__\s*=\s*[\"\']([\d.]+)[\"\']]', content)
if not m:
    m = re.search(r'__version__\s*=\s*[\"\']([\d.]+)[\"\']]', content.replace('\"', \"'\"))
# 简单匹配
import re
m2 = re.search(r'(\d+)\.(\d+)\.(\d+)', content)
if m2:
    major, minor, patch = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
    new_ver = f'{major}.{minor}.{patch+1}'
    new_content = content.replace(m2.group(0), new_ver, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f'版本号更新：{m2.group(0)} -> {new_ver}')
"
echo [打包] 开始打包，请稍候...
taskkill /F /IM "京东外卖抢券工具*" 2>nul
del /F /Q dist\*.exe 2>nul
rmdir /S /Q build 2>nul
pyinstaller build.spec --clean --noconfirm

echo.
echo [打包] 清理 dist 目录中的敏感文件...
if exist dist\data rmdir /S /Q dist\data
if exist dist\logs rmdir /S /Q dist\logs
mkdir dist\data
mkdir dist\logs

echo [打包] 更新 dist\config.yaml...
if not exist dist\config.yaml (
    copy /Y config.yaml dist\config.yaml >nul
    echo 已从根目录拷贝 config.yaml 到 dist\
)
python -c "
import yaml
path = 'dist/config.yaml'
with open(path, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
cfg['credential'] = {'cookie': ''}
with open(path, 'w', encoding='utf-8') as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
print('dist/config.yaml 已清理')
"
echo.
echo [完成] 打包完成，发布文件在 dist\ 目录下
echo [注意] 首次运行需要确保电脑已安装 Microsoft Edge 浏览器
pause
