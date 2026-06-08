"""
领券执行器模块（Playwright 浏览器自动化版）

流程：
1. 程序启动时预热浏览器，打开活动页面
2. 调度器触发时，持续刷新页面（每次加载完立即扫描，约每秒一次）
3. 检测到「立即抢券」按钮立即点击
4. 解析结果并返回
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.models import (
    ClaimResult,
    ClaimStatus,
    CouponInfo,
    CouponTargetConfig,
    FailReason,
)




class CrawlerError(Exception):
    login_expired: bool = False


class CrawlerTimeoutError(CrawlerError):
    pass


class CouponCrawler:
    """领券执行器：用 Playwright 控制 Edge 浏览器自动抢券。"""

    def __init__(
        self,
        session,
        targets: list[CouponTargetConfig],
        timeout: tuple[int, int],
        logger: logging.Logger,
        jd_area: str = "",
        cookie: str = "",
        headless: bool = False,
        on_credential_updated=None,
        grab_interval_ms: int = 0,
    ) -> None:
        self._targets = targets
        self._timeout = timeout
        self._logger = logger
        self._jd_area = jd_area
        self._session_cookie = cookie
        self._headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._on_credential_updated = on_credential_updated
        self._grab_interval_ms = grab_interval_ms  # 刷新间隔（毫秒）
        self._stopped = False  # 是否已主动关闭，防止 close() 后 _ensure_browser() 重新启动

    def set_session_cookie(self, session_cookie: str) -> None:
        self._session_cookie = session_cookie

    def _parse_cookies(self) -> list[dict]:
        cookies = []
        for part in self._session_cookie.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            name, _, value = part.partition("=")
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".jd.com",
                "path": "/",
            })
        return cookies

    def _ensure_browser(self) -> None:
        """确保浏览器已启动并完成预热，如果没有则启动。"""
        # 已调用 close() 主动停止，不再重新启动
        if self._stopped:
            raise CrawlerError("爬虫已停止，不允许重新启动浏览器")

        from playwright.sync_api import sync_playwright

        if self._browser is not None:
            try:
                connected = self._browser.is_connected()
            except Exception:
                connected = False
            # 同时检查 page 是否还活着
            page_ok = False
            if connected and self._page is not None:
                try:
                    _ = self._page.url  # 访问属性，page 关闭时会抛异常
                    page_ok = True
                except Exception:
                    page_ok = False
            if connected and page_ok:
                return
            self._logger.warning("浏览器或页面已关闭，重新启动")
            try:
                self.close()
            except Exception:
                pass
            self._browser = None
            self._context = None
            self._page = None

        self._logger.info("启动 Edge 浏览器（%s）", "无头模式" if self._headless else "常驻模式")
        self._playwright = sync_playwright().start()

        # 自动查找 Edge 可执行文件路径（兼容系统级和用户级安装）
        import os as _os
        _edge_candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            _os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        ]
        _edge_exe = next((p for p in _edge_candidates if _os.path.exists(p)), None)

        if _edge_exe:
            self._logger.info("使用 Edge 路径：%s", _edge_exe)
            self._browser = self._playwright.chromium.launch(
                executable_path=_edge_exe,
                headless=self._headless,
            )
        else:
            # 回退到 channel 方式
            self._browser = self._playwright.chromium.launch(
                channel="msedge",
                headless=self._headless,
            )
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            device_scale_factor=3,
        )

        if self._session_cookie:
            self._context.add_cookies(self._parse_cookies())
            self._logger.info("已注入登录凭证")

        # 注入反检测脚本，覆盖 webdriver 标志
        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            window.chrome = { runtime: {} };
        """)

        # 注入额外请求头，模拟真实浏览器行为
        self._context.set_extra_http_headers({
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Referer": "https://hour.jd.com/",
            "Origin": "https://hour.jd.com",
            "sec-ch-ua": '"Chromium";v="124", "Android WebView";v="124"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
        })

        self._page = self._context.new_page()

        # 预热：首次打开页面
        if not self._targets:
            raise CrawlerError("未配置 coupon_targets，无法启动浏览器")
        url = self._targets[0].url
        self._logger.info("预热：打开活动页面")
        try:
            self._page.goto(url, timeout=30000, wait_until="domcontentloaded")
        except Exception as exc:
            self._logger.warning("预热页面加载异常：%s，继续...", exc)

        # 检测是否跳转到登录页，若是则等待用户登录
        try:
            self._wait_for_login_if_needed(self._page, url)
        except Exception as exc:
            self._logger.warning("登录检测异常：%s", exc)

        # 额外检测：凭证文件不存在，或文件存在但密钥不匹配/文件损坏无法解密
        # 这两种情况都需要重新登录，主动跳转到登录页等待用户操作
        import os as _os
        _need_login = False
        if not _os.path.exists("data/credentials.enc"):
            self._logger.warning("凭证文件不存在，需要登录...")
            _need_login = True
        else:
            try:
                with open("data/credentials.enc", "rb") as _f:
                    _ciphertext = _f.read()
                if _os.path.exists("data/fernet.key"):
                    from cryptography.fernet import Fernet as _Fernet
                    with open("data/fernet.key", "rb") as _f:
                        _key = _f.read()
                    _Fernet(_key).decrypt(_ciphertext)
                    self._logger.info("凭证文件验证通过")
                else:
                    self._logger.warning("密钥文件不存在，需要重新登录...")
                    _need_login = True
            except Exception as _e:
                self._logger.warning("凭证文件无法解密（%s），需要重新登录...", _e)
                _need_login = True

        if _need_login:
            try:
                self._page.goto(
                    "https://plogin.m.jd.com/login/login",
                    timeout=15000,
                    wait_until="domcontentloaded",
                )
                self._wait_for_login_if_needed(self._page, url)
            except Exception as exc:
                self._logger.warning("主动登录异常：%s", exc)

        try:
            self._page.wait_for_selector(".coupon-button-section", timeout=20000)
        except Exception:
            try:
                self._page.wait_for_timeout(5000)
            except Exception:
                pass
        self._logger.info("浏览器预热完成")

    def _wait_for_login_if_needed(self, page, target_url: str) -> None:
        """
        检测当前页面是否为登录页。
        若是，等待用户在浏览器中手动完成登录（手机号验证码或密码登录），
        登录后自动提取并保存 cookie，跳回活动页。
        """
        _LOGIN_DOMAINS = ("passport.jd.com", "plogin.m.jd.com", "login.jd.com")

        def _is_login_page() -> bool:
            return any(d in page.url for d in _LOGIN_DOMAINS)

        if not _is_login_page():
            return

        self._logger.warning("检测到登录页，请在浏览器中完成登录...")
        print("\n[登录] 检测到需要登录，请在浏览器中手动完成登录。")
        print("[登录] 登录完成后程序将自动继续。\n")

        # 等待跳离登录页（最多 5 分钟）
        try:
            page.wait_for_function(
                "() => !window.location.href.includes('passport.jd.com') "
                "&& !window.location.href.includes('plogin.m.jd.com') "
                "&& !window.location.href.includes('login.jd.com')",
                timeout=300_000,
            )
        except Exception:
            self._logger.error("等待登录超时（5分钟），请检查网络或重试")
            raise CrawlerError("等待用户登录超时")

        self._logger.info("登录成功，自动提取 Cookie")
        print("[登录] 登录成功，正在自动保存 Cookie...\n")

        cookie_str = self._extract_cookie_from_browser()
        if cookie_str:
            self._session_cookie = cookie_str
            if self._on_credential_updated:
                try:
                    self._on_credential_updated(cookie_str)
                    self._logger.info("登录凭证已自动保存，后续任务无需重新登录")
                except Exception as exc:
                    self._logger.warning("保存 Cookie 回调失败：%s", exc)
        else:
            self._logger.warning("未能提取到登录凭证，请检查是否登录成功")

        # 跳回目标页面
        page.goto(target_url, timeout=30000, wait_until="domcontentloaded")

    def _extract_cookie_from_browser(self) -> str:
        """从当前浏览器 context 提取所有 .jd.com 登录凭证，拼成 key=value; 字符串。"""
        try:
            cookies = self._context.cookies()
            parts = [f"{c['name']}={c['value']}" for c in cookies if "jd.com" in c.get("domain", "")]
            return "; ".join(parts)
        except Exception as exc:
            self._logger.warning("提取浏览器登录凭证失败：%s", exc)
            return ""

    def warmup(self) -> None:
        """预热入口，保留接口兼容性，实际浏览器在任务触发时启动。"""
        self._logger.info("工作进程已就绪，等待调度触发时启动浏览器")

    def close(self) -> None:
        """关闭浏览器，程序退出时调用。"""
        self._stopped = True  # 标记已停止，阻止 _ensure_browser() 重新启动
        try:
            if self._context:
                try:
                    self._context.close()
                except Exception:
                    pass
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None

    def run(self, force: bool = False) -> list[ClaimResult]:
        """执行领券流程。浏览器全程保持开着，直接复用。"""
        from playwright.sync_api import TimeoutError as PWTimeout

        # 确保浏览器还活着（用户可能手动关闭了）
        self._ensure_browser()

        try:
            return self._grab_coupons(self._page, force=force)
        except PWTimeout:
            self._logger.error("页面操作超时")
            raise CrawlerTimeoutError("Playwright 操作超时")
        except CrawlerError:
            raise
        except Exception as exc:
            # 浏览器被关闭时，重置状态，下次任务重新启动
            self._logger.exception("浏览器操作异常：%s", exc)
            self.close()
            raise CrawlerError(f"浏览器操作异常：{exc}") from exc

    def _grab_coupons(self, page, force: bool = False) -> list[ClaimResult]:
        """
        轮询刷新页面抢券。

        时间窗口根据调度触发时的分钟数动态计算：
        - 触发分钟:30 前等待
        - 触发分钟:30~:55 预备（打开页面）
        - 触发分钟:55 开始刷新
        - 触发分钟+1:30 结束
        """
        from playwright.sync_api import TimeoutError as PWTimeout

        if not self._targets:
            raise CrawlerError("未配置 coupon_targets，无法执行领券")
        url = self._targets[0].url
        coupon_info = CouponInfo(
            coupon_id="grab_0",
            name="百补好运券",
            denomination=4.0,
            min_spend=5.0,
            claim_url=url,
        )
        clicked = False
        self._preheat_done = False
        risk_control_count = 0          # 连续出现「销售火爆」的次数
        RISK_CONTROL_THRESHOLD = 8      # 连续 N 次才判定为风控

        # 记录触发时的分钟数，用于动态计算时间窗口
        trigger_minute = datetime.now().minute
        # 开抢分钟 = 触发分钟 + 1（如触发 29 分，开抢 30 分）
        open_minute = (trigger_minute + 1) % 60

        # 各阶段时间（秒）
        ready_start   = trigger_minute * 60 + 30   # 触发分钟:30 开始预备
        preheat_time  = trigger_minute * 60 + 50   # 触发分钟:50 预热刷新一次
        refresh_start = trigger_minute * 60 + 55   # 触发分钟:55 开始正常刷新
        stop_time     = open_minute * 60 + 25       # 开抢分钟:25 结束

        # 预热刷新触发时间：在 :50 正负随机 1000ms，只在任务开始时随机一次
        import random as _r
        preheat_trigger = preheat_time + _r.randint(-1000, 1000) / 1000.0
        self._logger.info("本次预热刷新时间点：%d:%02d:%.1f",
                          datetime.now().hour, trigger_minute, preheat_trigger % 60)

        for attempt in range(60):
            if not force:
                now = datetime.now()
                total_seconds = now.minute * 60 + now.second

                # 预备前等待
                if total_seconds < ready_start:
                    wait_secs = ready_start - total_seconds
                    self._logger.info("距离 %d:%02d:30 还有 %d 秒，等待中...", now.hour, trigger_minute, wait_secs)
                    page.wait_for_timeout(min(wait_secs * 1000, 5000))
                    continue

                # 预备阶段：打开页面，并在 :50 预热刷新一次
                if total_seconds < refresh_start:
                    if attempt == 0:
                        self._logger.info("进入预备阶段，打开活动页面...")
                        try:
                            page.goto(url, timeout=15000, wait_until="domcontentloaded")
                        except Exception:
                            pass
                # 到达随机预热时间点时刷新一次
                if not getattr(self, '_preheat_done', False):
                    if total_seconds >= preheat_trigger:
                        self._logger.info("预热刷新（随机时间点 %.1f 秒）...", preheat_trigger % 60)
                        try:
                            page.reload(wait_until="domcontentloaded", timeout=5000)
                        except Exception:
                            pass
                        self._preheat_done = True
                    wait_secs = refresh_start - total_seconds
                    self._logger.info("预备中，距离 %d:%02d:55 还有 %d 秒...", now.hour, trigger_minute, wait_secs)
                    page.wait_for_timeout(min(wait_secs * 1000, 1000))
                    continue

                # 预热已完成但还没到 :55，继续等待
                if total_seconds < refresh_start:
                    wait_secs = refresh_start - total_seconds
                    self._logger.info("预热完成，距离 %d:%02d:55 还有 %d 秒，等待中...", now.hour, trigger_minute, wait_secs)
                    page.wait_for_timeout(min(wait_secs * 1000, 1000))
                    continue

                # 结束时间后停止（如果已点击过，再给一轮确认结果）
                if total_seconds >= stop_time:
                    if clicked and attempt < 59:
                        # 已点击，再刷一次看结果
                        self._logger.info("时间到但已点击，再刷一次确认结果...")
                    else:
                        self._logger.info("已过 %d:%02d:25，停止轮询", now.hour, open_minute)
                        break
            else:
                # force 模式（测试效果）：最多刷 20 次后停止
                if attempt >= 20:
                    self._logger.info("测试效果：已刷新 20 次，停止")
                    break

            # 记录本轮开始时间，保证最小刷新间隔 1 秒
            loop_start = datetime.now().timestamp()

            try:
                # reload 触发数据刷新，等券状态接口返回即可扫按钮，不等整页加载完
                with page.expect_response(
                    lambda r: "hours_home_pub" in r.url and r.status == 200,
                    timeout=1500
                ):
                    page.reload(wait_until="commit")
            except Exception as reload_exc:
                self._logger.warning("页面刷新异常：%s", reload_exc)
            if self._grab_interval_ms > 0:
                page.wait_for_timeout(self._grab_interval_ms)

            # 检查登录状态
            if "login" in page.url.lower() or "passport" in page.url.lower():
                self._wait_for_login_if_needed(page, url)
                page.wait_for_timeout(2000)
                continue

            # 检查页面是否出现风控提示「销售火爆，请稍后再试」
            try:
                page_text = page.content()
                if "销售火爆" in page_text and "请稍后再试" in page_text:
                    risk_control_count += 1
                    self._logger.warning(
                        "页面出现「销售火爆，请稍后再试」（连续第 %d 次）%s",
                        risk_control_count,
                        "，继续刷新..." if risk_control_count < RISK_CONTROL_THRESHOLD else f"，连续 {RISK_CONTROL_THRESHOLD} 次刷新提示销售火爆，判定可能为风控，暂时终止抢券",
                    )
                    if risk_control_count >= RISK_CONTROL_THRESHOLD:
                        return [ClaimResult(
                            coupon_info=coupon_info,
                            status=ClaimStatus.FAILED,
                            fail_reason=FailReason.OUT_OF_STOCK,
                        )]
                else:
                    risk_control_count = 0  # 不连续，重置计数
            except Exception:
                pass

            # 切换到「正在抢券中」tab，找不到就扫当前页面
            now_check = datetime.now()
            check_seconds = now_check.minute * 60 + now_check.second
            after_open = check_seconds >= open_minute * 60 + 6

            ongoing_tab = None
            try:
                tabs = page.locator(".grab-coupon-floor__tab-item").all()
                for tab in tabs:
                    try:
                        status_text = tab.locator(".grab-coupon-floor__tab-status").inner_text(timeout=200).strip()
                        self._logger.info("Tab 状态：%s", status_text)
                        if status_text in ("正在抢券中", "抢券中"):
                            tab.click(timeout=1500)
                            page.wait_for_timeout(200)
                            ongoing_tab = tab
                            self._logger.info("已切换到「正在抢券中」tab")
                            break
                    except Exception:
                        pass
            except Exception:
                pass

            btn_sections = page.locator(".coupon-button-section").all()
            found_action = False
            for section in btn_sections:
                try:
                    text = section.locator(".coupon-button-text").inner_text(timeout=300).strip()
                    self._logger.info("按钮文字：%s", text)

                    if text in ("立即抢券", "立即领取"):
                        self._logger.info("发现可抢按钮，1秒内随机间隔连点3次")
                        import random as _random
                        for i in range(3):
                            try:
                                # dispatch_event 直接派发点击事件，不等待页面响应，
                                # 确保 3 次点击在 1 秒内完成
                                section.dispatch_event("click")
                                self._logger.info("第 %d 次点击", i + 1)
                            except Exception:
                                pass
                            if i < 2:
                                page.wait_for_timeout(_random.randint(200, 500))
                        clicked = True
                        risk_control_count = 0
                        found_action = True
                        # 点击后等待 800ms 再进入下一轮 reload，
                        # 给服务端处理时间，减少紧跟其后的接口超时 warning
                        page.wait_for_timeout(800)
                        # 捕获点击后页面弹出的 toast 提示并写入日志
                        self._log_toast(page)
                        break

                    if text in ("销售火爆，请稍后再试",):
                        risk_control_count += 1
                        self._logger.warning(
                            "按钮显示「销售火爆，请稍后再试」（连续第 %d 次）%s",
                            risk_control_count,
                            "，继续刷新..." if risk_control_count < RISK_CONTROL_THRESHOLD else f"，连续 {RISK_CONTROL_THRESHOLD} 次刷新提示销售火爆，判定可能为风控，暂时终止抢券",
                        )
                        if risk_control_count >= RISK_CONTROL_THRESHOLD:
                            return [ClaimResult(
                                coupon_info=coupon_info,
                                status=ClaimStatus.FAILED,
                                fail_reason=FailReason.OUT_OF_STOCK,
                            )]
                        break  # 本轮跳出按钮扫描，继续下一轮刷新

                    # 结束条件：只在「正在抢券中」tab 下判断
                    if (not force) and after_open and ongoing_tab is not None:
                        if text == "已领取":
                            self._logger.info("「正在抢券中」tab 显示「已领取」，抢券成功")
                            return [ClaimResult(
                                coupon_info=coupon_info,
                                status=ClaimStatus.SUCCESS,
                                claimed_at=datetime.now(),
                            )]
                        if text in ("已使用", "已抢光", "已抢完", "已售罄", "库存不足"):
                            self._logger.info("「正在抢券中」tab 显示「%s」，没有抢到，结束", text)
                            return [ClaimResult(
                                coupon_info=coupon_info,
                                status=ClaimStatus.FAILED,
                                fail_reason=FailReason.OUT_OF_STOCK,
                            )]
                except Exception:
                    pass

            if not clicked:
                self._logger.info("暂无可抢按钮，继续刷新...")

            # 每轮随机间隔 1300~1700ms，避免固定频率被风控
            import random
            elapsed = datetime.now().timestamp() - loop_start
            min_interval = random.randint(1300, 1600) / 1000.0
            if elapsed < min_interval:
                page.wait_for_timeout(int((min_interval - elapsed) * 1000))

        self._logger.info("轮询结束，未能抢到券")
        return []

    def _switch_to_ongoing_tab(self, page) -> None:
        """找到「正在抢券中」的 tab 并点击，等待内容渲染。"""
        try:
            tabs = page.locator(".grab-coupon-floor__tab-item").all()
            for tab in tabs:
                try:
                    status_el = tab.locator(".grab-coupon-floor__tab-status")
                    status_text = status_el.inner_text(timeout=500).strip()
                    self._logger.info("Tab 状态：%s", status_text)
                    if status_text in ("正在抢券中", "抢券中"):
                        tab.click(timeout=3000)
                        page.wait_for_timeout(300)  # 等待 tab 内容渲染
                        self._logger.info("已切换到「正在抢券中」tab")
                        return
                except Exception:
                    pass
        except Exception as exc:
            self._logger.debug("切换 tab 失败：%s", exc)

    def _check_result(self, page, coupon_info: CouponInfo) -> ClaimResult:
        """检查抢券后页面提示，判断成功或失败。"""
        page.wait_for_timeout(500)
        page_text = page.content()

        if any(kw in page_text for kw in ["领取成功", "抢券成功", "已放入", "去使用"]):
            return ClaimResult(
                coupon_info=coupon_info,
                status=ClaimStatus.SUCCESS,
                claimed_at=datetime.now(),
            )
        if any(kw in page_text for kw in ["已领取", "已抢到", "已使用"]):
            return ClaimResult(
                coupon_info=coupon_info,
                status=ClaimStatus.SKIPPED,
                fail_reason=FailReason.ALREADY_CLAIMED,
            )
        if any(kw in page_text for kw in ["已抢完", "库存不足", "已售罄", "已抢光"]):
            return ClaimResult(
                coupon_info=coupon_info,
                status=ClaimStatus.FAILED,
                fail_reason=FailReason.OUT_OF_STOCK,
            )
        if any(kw in page_text for kw in ["未开始", "即将开抢", "待开抢"]):
            return ClaimResult(
                coupon_info=coupon_info,
                status=ClaimStatus.FAILED,
                fail_reason=FailReason.NOT_STARTED,
            )
        # 系统繁忙/网络异常，应继续重试，复用 NOT_STARTED 触发重试逻辑
        if any(kw in page_text for kw in ["系统繁忙", "稍后重试", "网络异常", "请求失败", "服务异常"]):
            self._logger.warning("系统繁忙，继续重试...")
            return ClaimResult(
                coupon_info=coupon_info,
                status=ClaimStatus.FAILED,
                fail_reason=FailReason.NOT_STARTED,
            )

        # 默认记为成功（点击后无明显失败提示）
        self._logger.info("未检测到明确结果提示，默认记为成功")
        return ClaimResult(
            coupon_info=coupon_info,
            status=ClaimStatus.SUCCESS,
            claimed_at=datetime.now(),
        )

    def _log_toast(self, page, prefix: str = "") -> None:
        """
        捕获页面上当前可见的 toast 提示文字并写入日志。

        京东页面常见 toast 容器选择器（按优先级依次尝试）：
          - .vip-toast（旧版）
          - .sku-toast（商品详情页）
          - .o2-toast（新版通用）
          - .tips-toast
          - [class*="toast"]（兜底，匹配所有带 toast 的类名）

        在每次点击「立即抢券」/「立即领取」按钮后、页面 reload 前调用，
        不修改页面状态，所有异常均静默忽略，不影响主流程。
        """
        _TOAST_SELECTORS = [
            ".vip-toast",
            ".sku-toast",
            ".o2-toast",
            ".tips-toast",
            "[class*='toast']",
        ]
        # 成功/失败关键词对应日志级别
        _SUCCESS_KEYWORDS = {"领取成功", "抢券成功", "已放入", "去使用", "已领取", "抢到了"}
        _WARN_KEYWORDS    = {"领取失败", "请稍后重试", "系统繁忙", "网络异常", "销售火爆",
                             "已抢完", "已售罄", "库存不足", "已抢光", "活动已结束"}

        seen: set[str] = set()
        for selector in _TOAST_SELECTORS:
            try:
                els = page.locator(selector).all()
                for el in els:
                    try:
                        if not el.is_visible(timeout=200):
                            continue
                        msg = el.inner_text(timeout=300).strip()
                        if not msg or msg in seen:
                            continue
                        seen.add(msg)
                        if any(kw in msg for kw in _SUCCESS_KEYWORDS):
                            self._logger.info("%sToast 提示：%s", prefix, msg)
                        elif any(kw in msg for kw in _WARN_KEYWORDS):
                            self._logger.warning("%sToast 提示：%s", prefix, msg)
                        else:
                            self._logger.info("%sToast 提示：%s", prefix, msg)
                    except Exception:
                        pass
            except Exception:
                pass

    def _close_popup(self, page) -> None:
        """尝试关闭弹窗。"""
        try:
            close_btn = page.locator("text=关闭, text=×, text=✕").first
            if close_btn.is_visible(timeout=1000):
                close_btn.click()
        except Exception:
            pass

    def idle_check(self) -> None:
        """
        闲时巡检：轻量刷新一次活动页面，扫描是否有可领取优惠券。
        发现「立即抢券」或「立即领取」按钮则点击并记录日志，否则静默返回。
        不抛出异常，所有错误仅记录警告日志。
        """
        if not self._targets:
            return
        url = self._targets[0].url

        # 若浏览器未启动（从未预热或已关闭），不在 idle_check 里重新启动，
        # 避免停止过程中意外弹出浏览器
        if self._browser is None or self._page is None:
            return
        try:
            connected = self._browser.is_connected()
        except Exception:
            connected = False
        if not connected:
            return

        page = self._page

        try:
            # 检查登录状态，不阻塞（不等待登录）
            if "login" in page.url.lower() or "passport" in page.url.lower():
                self._logger.info("闲时巡检：检测到登录页，跳过本次")
                return

            # 轻量刷新：等接口返回即可，不等完整页面
            try:
                with page.expect_response(
                    lambda r: "hours_home_pub" in r.url and r.status == 200,
                    timeout=2000,
                ):
                    page.reload(wait_until="commit")
            except Exception:
                # 接口未响应也继续扫描，页面可能已有内容
                pass

            # 再次检查登录状态
            if "login" in page.url.lower() or "passport" in page.url.lower():
                self._logger.info("闲时巡检：刷新后跳转到登录页，跳过本次")
                return

            # 扫描按钮
            btn_sections = page.locator(".coupon-button-section").all()
            for section in btn_sections:
                try:
                    text = section.locator(".coupon-button-text").inner_text(timeout=300).strip()
                    if text in ("立即抢券", "立即领取"):
                        self._logger.info("闲时巡检：发现可领取按钮「%s」，尝试点击", text)
                        import random as _r
                        for i in range(3):
                            try:
                                section.dispatch_event("click")
                                self._logger.info("闲时巡检：第 %d 次点击", i + 1)
                            except Exception:
                                pass
                            if i < 2:
                                page.wait_for_timeout(_r.randint(200, 500))
                        # 等待一下看结果
                        page.wait_for_timeout(800)
                        # 捕获点击后页面弹出的 toast 提示并写入日志
                        self._log_toast(page, prefix="闲时巡检：")
                        try:
                            result_text = page.content()
                            if any(kw in result_text for kw in ["领取成功", "抢券成功", "已放入", "去使用", "已领取"]):
                                self._logger.info("闲时巡检：领取成功")
                            else:
                                self._logger.info("闲时巡检：点击完成，页面无明确成功提示")
                        except Exception:
                            pass
                        return  # 点过一次就返回，不继续扫下一个
                except Exception:
                    pass

            self._logger.debug("闲时巡检：页面无可领取按钮")

        except Exception as exc:
            self._logger.warning("闲时巡检：执行异常：%s", exc)
