#!/usr/bin/env python3
"""Web 管理界面入口"""
import os
import sys


def run_web():
    port = int(os.environ.get("WEB_PORT", 8080))
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")

    from src.web.app import create_app
    app = create_app(config_path=config_path)

    print(f"[启动] 京东外卖券管理界面已启动：http://localhost:{port}")
    print("按 Ctrl+C 停止")

    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port)
    except OSError as e:
        if "address already in use" in str(e).lower() or "10048" in str(e):
            print(f"[错误] 端口 {port} 已被占用，请更换端口（设置环境变量 WEB_PORT）")
            sys.exit(1)
        raise


if __name__ == "__main__":
    run_web()
