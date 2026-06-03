#!/usr/bin/env python3
"""
京东定时外卖优惠券自动领取工具

用法：
    python main.py                  # 启动系统托盘模式
    python main.py --port 8080      # 指定端口
    python main.py --config x.yaml  # 指定配置文件
    python main.py --worker ...     # 内部用，由 Web 界面启动工作进程（勿手动调用）
"""

import argparse
import sys
import threading
import time
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="京东定时外卖优惠券自动领取工具")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--port", type=int, default=5000, help="Web 界面端口（默认 5000）")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-now", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--once", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    # worker 模式：转发给 worker.py
    if args.worker:
        import worker as w
        sys.argv = [sys.argv[0], "--config", args.config]
        if args.run_now:
            sys.argv.append("--run-now")
        if args.once:
            sys.argv.append("--once")
        w.main()
        return

    web_url = f"http://localhost:{args.port}"

    # 启动 Web 服务
    _start_web_server(args.config, args.port)
    time.sleep(1)  # 等 Web 服务启动

    # 启动系统托盘
    _run_tray(web_url)


_flask_app = None  # 保存 Flask app 引用，供退出时访问


def _start_web_server(config_path: str, port: int) -> None:
    """在后台线程启动 Flask Web 服务。"""
    global _flask_app
    from src.web.app import create_app

    _flask_app = create_app(config_path=config_path)

    def _run():
        try:
            from waitress import serve
            serve(_flask_app, host="127.0.0.1", port=port, threads=4)
        except OSError as e:
            if "10048" in str(e) or "address already in use" in str(e).lower():
                print(f"[错误] 端口 {port} 已被占用，请用 --port 换一个端口")
            else:
                print(f"[错误] Web 服务启动失败：{e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _run_tray(web_url: str) -> None:
    """启动系统托盘图标。"""
    import pystray
    from PIL import Image, ImageDraw

    # 生成托盘图标
    def _make_icon():
        from PIL import Image
        import os
        # 优先使用 static/logo.png
        base = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base, "static", "logo.png")
        if not os.path.exists(logo_path):
            # 打包后路径
            logo_path = os.path.join(os.path.dirname(sys.executable), "static", "logo.png")
        if os.path.exists(logo_path):
            return Image.open(logo_path).convert("RGBA").resize((64, 64))
        # 找不到图片时用默认图标
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(220, 50, 50, 255))
        draw.text((18, 18), "JD", fill=(255, 255, 255, 255))
        return img

    def _open_web(icon, item):
        webbrowser.open(web_url)

    def _quit(icon, item):
        icon.stop()
        # 通过 SchedulerController 正确终止 worker 子进程
        # 先写 flag 让 worker 优雅退出，若 5 秒内未退出则强杀
        try:
            if _flask_app is not None:
                controller = _flask_app.extensions.get("scheduler_controller")
                if controller is not None:
                    controller.stop_immediately()
        except Exception:
            pass
        # 用 os._exit 强制终止，避免 waitress/pystray 残留线程导致僵尸进程
        import os
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("打开管理界面", _open_web, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", _quit),
    )

    icon = pystray.Icon(
        name="coupon_tool",
        icon=_make_icon(),
        title="京东外卖定时优惠券抢券助手",
        menu=menu,
    )

    # 托盘启动后自动打开管理界面
    def _on_setup(icon):
        icon.visible = True
        webbrowser.open(web_url)

    icon.run(_on_setup)


if __name__ == "__main__":
    main()
