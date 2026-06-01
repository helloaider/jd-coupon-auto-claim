#!/usr/bin/env python3
"""
抢券工作进程入口

由 Web 界面通过 subprocess 启动，负责：
1. 验证登录状态（需要时弹出浏览器扫码）
2. 在主线程循环等待触发时间，到时间直接执行抢券
3. 浏览器全程保持开着，不关不重开

用法：
    python worker.py --config config.yaml
    python worker.py --config config.yaml --once   # 立即执行一次后退出
"""

import argparse
import os
import sys
import time
from datetime import datetime


def _parse_cron_minutes(cron_list: list[str]) -> list[int]:
    """从 cron 表达式列表提取触发的分钟数，如 '29 10 * * *' → 29。"""
    minutes = []
    for cron in cron_list:
        parts = cron.strip().split()
        if len(parts) >= 2:
            try:
                minutes.append(int(parts[0]))
            except ValueError:
                pass
    return list(set(minutes))


def _should_trigger(schedule: list[str], last_trigger_key: str) -> tuple[bool, str]:
    """
    检查当前时间是否应该触发任务。
    返回 (should_trigger, trigger_key)
    trigger_key 格式：YYYY-MM-DD HH:MM，防止同一分钟重复触发。
    """
    now = datetime.now()
    for cron in schedule:
        parts = cron.strip().split()
        if len(parts) < 2:
            continue
        try:
            minute = int(parts[0])
            hour = int(parts[1]) if parts[1] != '*' else -1
        except ValueError:
            continue

        if now.minute == minute and (hour == -1 or now.hour == hour):
            key = now.strftime(f"%Y-%m-%d %H:{minute:02d}")
            if key != last_trigger_key:
                return True, key

    return False, last_trigger_key


def main() -> None:
    parser = argparse.ArgumentParser(description="抢券工作进程")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--once", action="store_true", help="立即执行一次后退出（临时测试用）")
    parser.add_argument("--run-now", action="store_true", help="立即执行一次后继续等待调度")
    args = parser.parse_args()

    import requests
    from src.auth_manager import AuthManager, CredentialInvalidError, KeyFileNotFoundError
    from src.config_loader import ConfigLoader, ConfigValidationError
    from src.coupon_crawler import CouponCrawler
    from src.logger_setup import setup_logger
    from src.task_runner import TaskRunner

    # 加载配置
    try:
        config = ConfigLoader().load(args.config)
    except (ConfigValidationError, FileNotFoundError) as e:
        print(f"[错误] 配置加载失败：{e}", flush=True)
        sys.exit(1)

    logger = setup_logger(config.log)

    # 初始化 AuthManager
    auth_manager = AuthManager(
        config.credential, "data/credentials.enc", "data/fernet.key", logger
    )
    try:
        auth_manager.initialize()
    except CredentialInvalidError:
        logger.warning("未找到凭证，将在浏览器中等待用户登录")
    except KeyFileNotFoundError:
        print("[错误] 密钥文件丢失", flush=True)
        sys.exit(1)

    session = requests.Session()
    crawler = CouponCrawler(
        session,
        config.coupon_targets,
        config.request_timeout,
        logger,
        jd_area=config.jd_area,
        headless=config.headless,
        on_cookie_updated=auth_manager.update_cookie,
        grab_interval_ms=config.grab_interval_ms,
    )
    task_runner = TaskRunner(auth_manager, crawler, logger)

    # 注入 cookie
    try:
        headers = auth_manager.get_headers()
        crawler.set_cookie(headers.get("Cookie", ""))
    except Exception:
        pass

    # 启动时弹出浏览器（验证登录 / 让用户扫码）
    print("[工作进程] 正在启动浏览器...", flush=True)
    crawler._ensure_browser()
    print("[工作进程] 浏览器已就绪，等待触发时间...", flush=True)

    # 打印下次触发时间提示
    from src.config_loader import ConfigLoader as _CL
    try:
        _cfg = _CL().load(args.config)
        logger.info("调度计划：%s", "、".join(_cfg.schedule))
        logger.info("浏览器已就绪，等待调度触发时自动开始抢券")
    except Exception:
        pass

    # --once 模式：立即执行一次后退出
    if args.once:
        print("[工作进程] 临时测试：执行一次领券任务...", flush=True)
        try:
            task_runner.run(force=True)
        except Exception as e:
            logger.warning("临时测试执行异常：%s", e)
        finally:
            crawler.close()
            print("[工作进程] 临时测试完成，已退出", flush=True)
        sys.exit(0)  # 强制退出，不继续执行后续逻辑

    # --run-now 模式：立即执行一次后继续等待
    if args.run_now:
        print("[工作进程] 立即执行一次领券任务...", flush=True)
        task_runner.run(force=True)
        print("[工作进程] 执行完成，继续等待调度...", flush=True)

    # 主循环：在主线程里等待触发时间，避免 APScheduler 跨线程问题
    last_trigger_key = ""
    print(f"[工作进程] 调度循环已启动，共 {len(config.schedule)} 个触发时间", flush=True)
    for cron in config.schedule:
        print(f"  - {cron}", flush=True)

    # 捕获 SIGTERM，确保浏览器能正常关闭
    import signal
    try:
        def _handle_sigterm(signum, frame):
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, _handle_sigterm)
    except (OSError, ValueError):
        pass  # 打包环境或非主线程下 Windows 不支持 SIGTERM，忽略

    stop_flag = os.path.join("data", ".stop_worker")
    # 清理可能残留的旧标志
    try:
        os.remove(stop_flag)
    except Exception:
        pass

    try:
        while True:
            # 检测退出标志文件
            if os.path.exists(stop_flag):
                logger.info("检测到退出信号，正在关闭...")
                try:
                    os.remove(stop_flag)
                except Exception:
                    pass
                break
            should, last_trigger_key = _should_trigger(config.schedule, last_trigger_key)
            if should:
                logger.info("调度触发，开始执行领券任务")
                task_runner.run()
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        crawler.close()
        print("[工作进程] 已退出", flush=True)


if __name__ == "__main__":
    main()
