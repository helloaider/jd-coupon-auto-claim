#!/usr/bin/env python3
"""
领券工作进程入口

由 Web 界面通过 subprocess 启动，负责：
1. 验证登录状态（需要时弹出浏览器扫码）
2. 在主线程循环等待触发时间，到时间直接执行领券
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
    parser = argparse.ArgumentParser(description="领券工作进程")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--once", action="store_true", help="立即执行一次后退出（临时测试用）")
    parser.add_argument("--run-now", action="store_true", help="立即执行一次后继续等待调度")
    args = parser.parse_args()

    import requests
    from src.auth_manager import CredentialManager, LoginExpiredError, KeyFileNotFoundError
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

    # 初始化 CredentialManager
    auth_manager = CredentialManager(
        config.credential, "data/credentials.enc", "data/fernet.key", logger
    )
    try:
        auth_manager.initialize()
    except LoginExpiredError:
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
        on_credential_updated=auth_manager.update_credential,
        grab_interval_ms=config.grab_interval_ms,
    )
    task_runner = TaskRunner(
        auth_manager, crawler, logger,
        notify_email_cfg=getattr(config, "notify_email", None),
    )
    idle_check_enabled = getattr(config, "idle_check_enabled", False)
    idle_check_start_hour = getattr(config, "idle_check_start_hour", 10)
    idle_check_end_hour = getattr(config, "idle_check_end_hour", 18)
    try:
        headers = auth_manager.get_headers()
        crawler.set_session_cookie(headers.get("Cookie", ""))
    except Exception:
        pass

    # 启动时不立即弹浏览器，等到第一次任务触发时才启动
    # 这样停止任务/退出时不会先弹出浏览器再关闭
    print("[工作进程] 初始化完成，等待触发时间...", flush=True)

    # stop_flag 路径，供后续主循环和停止检测复用
    stop_flag = os.path.join("data", ".stop_worker")

    # 启动前检查停止标志（快速点启停时的保护）
    if os.path.exists(stop_flag):
        print("[工作进程] 检测到停止信号，取消启动", flush=True)
        try:
            os.remove(stop_flag)
        except Exception:
            pass
        return

    # 清理可能残留的旧标志（正常启动路径）
    try:
        os.remove(stop_flag)
    except Exception:
        pass

    # 启动前再次检查停止标志（防止在初始化阶段期间就已经收到停止信号）
    if os.path.exists(stop_flag):
        print("[工作进程] 启动浏览器前检测到停止信号，取消启动", flush=True)
        try:
            os.remove(stop_flag)
        except Exception:
            pass
        return

    # 启动时弹出浏览器（验证登录 / 让用户扫码）
    print("[工作进程] 正在启动浏览器...", flush=True)
    crawler._ensure_browser()
    print("[工作进程] 浏览器已就绪，等待触发时间...", flush=True)

    # 浏览器启动后再次检查停止标志：
    # 若用户在浏览器启动过程中点了停止，此时标志已写入，直接关闭浏览器退出。
    if os.path.exists(stop_flag):
        print("[工作进程] 浏览器启动后检测到停止信号，正在关闭浏览器...", flush=True)
        crawler._stopped = True
        try:
            os.remove(stop_flag)
        except Exception:
            pass
        crawler.close()
        print("[工作进程] 已退出", flush=True)
        return

    # 打印下次触发时间提示
    from src.config_loader import ConfigLoader as _CL
    try:
        _cfg = _CL().load(args.config)
        def _cron_to_time(expr: str) -> str:
            """将 'MM HH * * *' 格式的 cron 表达式转为 'HH:MM' 可读时间，无法解析则原样返回。"""
            parts = expr.strip().split()
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                return f"{int(parts[1]):02d}:{int(parts[0]):02d}"
            return expr

        readable = "、".join(_cron_to_time(e) for e in _cfg.schedule)
        logger.info("调度计划：每天 %s", readable)
        logger.info("浏览器已就绪，等待调度触发时自动开始领券")
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
    if idle_check_enabled:
        print(
            f"[工作进程] 闲时找券已启用（{idle_check_start_hour:02d}:01 ~ {idle_check_end_hour:02d}:56，"
            "每约 5 分钟巡检一次）",
            flush=True,
        )

    # 捕获 SIGTERM，确保浏览器能正常关闭
    import signal
    try:
        def _handle_sigterm(signum, frame):
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, _handle_sigterm)
    except (OSError, ValueError):
        pass  # 打包环境或非主线程下 Windows 不支持 SIGTERM，忽略

    # ---------------------------------------------------------------------------
    # 闲时巡检调度逻辑
    #
    # 节拍：每小时的 01/06/11/16/21/26/31/36/41/46/51/56 分，
    #       每次在该节拍分钟 ±60s 范围内随机一个秒级偏移触发。
    # 时间段：[idle_check_start_hour, idle_check_end_hour]（含两端小时的节拍）。
    # ---------------------------------------------------------------------------
    import random as _idle_rand

    # 固定节拍分钟列表
    _IDLE_BEAT_MINUTES = [1, 6, 11, 16, 21, 26, 31, 36, 41, 46, 51, 56]

    def _next_idle_check_ts() -> float:
        """
        从当前时刻起，找下一个节拍分钟（01/06/11/.../56），
        加上 ±60s 随机偏移，返回对应的 Unix 时间戳。
        若偏移后的时间比当前时间早（负偏移把时间推到过去），
        则顺延到再下一个节拍。
        """
        now = datetime.now()
        # 当前分钟对应的"整分"时间戳（秒为0）
        cur_minute_base = now.replace(second=0, microsecond=0)
        cur_total_minutes = now.hour * 60 + now.minute

        # 找下一个节拍（当前分钟之后的最近一个）
        candidate_ts = None
        # 搜索范围：当前分钟+1 到 当前分钟+60（最多找一个完整小时周期）
        for delta in range(1, 61):
            total = cur_total_minutes + delta
            h = (total // 60) % 24
            m = total % 60
            if m in _IDLE_BEAT_MINUTES:
                import calendar
                # 构造该节拍的"整分"时间戳
                beat_dt = cur_minute_base.replace(
                    hour=h, minute=m, second=0, microsecond=0
                )
                # 跨天时 beat_dt 可能比 cur_minute_base 小，需加1天
                if beat_dt < cur_minute_base:
                    from datetime import timedelta
                    beat_dt = beat_dt + timedelta(days=1)
                # 加随机偏移 ±60s
                offset = _idle_rand.randint(-60, 60)
                candidate_ts = beat_dt.timestamp() + offset
                # 若偏移后仍在当前时间之前，顺延到下一个节拍
                if candidate_ts <= time.time():
                    continue
                break

        if candidate_ts is None:
            # 保底：1 分钟后再算
            candidate_ts = time.time() + 60

        return candidate_ts

    def _is_in_idle_window() -> bool:
        """检查当前时间是否在闲时巡检的时间段内（start_hour 的 :01 到 end_hour 的 :56）。"""
        now = datetime.now()
        cur = now.hour * 60 + now.minute
        # start_hour:01 ~ end_hour:56
        start = idle_check_start_hour * 60 + 1
        end   = idle_check_end_hour   * 60 + 56
        return start <= cur <= end

    def _is_busy_window(schedule: list[str]) -> bool:
        """
        检查当前时间是否处于定点领券的忙时窗口（触发分钟:25 ~ 开抢分钟:30）。
        在此窗口内闲时巡检主动跳过，不干扰定点任务。
        """
        now = datetime.now()
        cur_seconds = now.minute * 60 + now.second
        for cron in schedule:
            parts = cron.strip().split()
            if len(parts) < 2:
                continue
            try:
                minute = int(parts[0])
                hour = int(parts[1]) if parts[1] != '*' else -1
            except ValueError:
                continue
            if hour != -1 and now.hour != hour:
                continue
            trigger_start = minute * 60 + 25
            open_end = ((minute + 1) % 60) * 60 + 30  # 开抢分钟:30 后完全结束（与领券结束时间 :25 留5s余量）
            # 跨分钟边界（如触发59分，开抢0分）
            if open_end < trigger_start:
                if cur_seconds >= trigger_start or cur_seconds <= open_end:
                    return True
            else:
                if trigger_start <= cur_seconds <= open_end:
                    return True
        return False

    next_idle_ts = _next_idle_check_ts() if idle_check_enabled else float("inf")

    try:
        while True:
            # 检测退出标志文件
            if os.path.exists(stop_flag):
                logger.info("检测到退出信号，正在关闭...")
                crawler._stopped = True  # 先标记，阻止任何后续路径重新启动浏览器
                try:
                    os.remove(stop_flag)
                except Exception:
                    pass
                break

            # 定点领券触发检测
            should, last_trigger_key = _should_trigger(config.schedule, last_trigger_key)
            if should:
                logger.info("调度触发，开始执行领券任务")
                task_runner.run()
                # 领券结束后重置闲时巡检时间，避免刚抢完立刻又巡检
                if idle_check_enabled:
                    next_idle_ts = _next_idle_check_ts()

            # 闲时巡检触发检测
            if idle_check_enabled and time.time() >= next_idle_ts:
                if not _is_in_idle_window():
                    logger.debug("闲时巡检：当前不在配置的时间段内，跳过，等待下一节拍")
                    next_idle_ts = _next_idle_check_ts()
                elif _is_busy_window(config.schedule):
                    logger.debug("闲时巡检：当前处于定点领券窗口，跳过本次")
                    # 延迟 60s 后重新判断（等窗口结束）
                    next_idle_ts = time.time() + 60
                else:
                    logger.info("闲时巡检：开始巡检活动页面")
                    crawler.idle_check()
                    next_idle_ts = _next_idle_check_ts()

            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        crawler.close()
        print("[工作进程] 已退出", flush=True)


if __name__ == "__main__":
    main()
