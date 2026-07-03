# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all

# 动态查找 playwright-stealth 的 JS 文件路径
import playwright_stealth
_stealth_js_dir = os.path.join(os.path.dirname(playwright_stealth.__file__), 'js')

# 读取版本号（从 src/version.py）
sys.path.insert(0, os.path.abspath('.'))
from src.version import __version__

APP_NAME = "京东外卖定时优惠券领券助手"

block_cipher = None

# 强制收集整个 Pillow 包（hiddenimports 不足以覆盖所有子模块）
pillow_datas, pillow_binaries, pillow_hiddenimports = collect_all('PIL')

a = Analysis(
    ['main.py', 'worker.py'],
    pathex=['.'],
    binaries=pillow_binaries,
    datas=[
        ('static', 'static'),          # Web 前端静态文件
        (_stealth_js_dir, 'playwright_stealth/js'),  # playwright-stealth JS 文件
    ] + pillow_datas,
    hiddenimports=[
        'waitress',
        'waitress.server',
        'waitress.task',
        'waitress.channel',
        'waitress.runner',
        'flask',
        'flask.templating',
        'apscheduler',
        'apscheduler.schedulers.blocking',
        'apscheduler.schedulers.background',
        'apscheduler.executors.pool',
        'apscheduler.triggers.cron',
        'apscheduler.events',
        'cryptography',
        'cryptography.fernet',
        'playwright',
        'playwright.sync_api',
        'playwright_stealth',
        'playwright_stealth.stealth',
        'yaml',
        'pydantic',
        'requests',
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
    ] + pillow_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除 Anaconda 自带的大型包，减小 exe 体积
        'IPython', 'ipykernel', 'ipython_genutils',
        'jupyter', 'jupyter_client', 'jupyter_core',
        'notebook', 'nbformat', 'nbconvert',
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'cv2', 'sklearn',
        'tornado', 'zmq', 'pygments',
        'tkinter', 'wx', 'PyQt5', 'PyQt6',
        'sphinx', 'docutils',
        'pytest', 'unittest',
        'setuptools', 'pkg_resources',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # 托盘模式，不显示终端窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='static/logo.ico',
)
