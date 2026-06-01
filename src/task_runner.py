"""
任务编排器模块

串联 AuthManager、CouponCrawler，编排单次领券任务的完整执行流程。
"""

from __future__ import annotations

import logging
from datetime import datetime

from .auth_manager import AuthManager, CredentialInvalidError
from .coupon_crawler import CouponCrawler, CrawlerError


class TaskRunner:
    """单次领券任务编排器。"""

    def __init__(
        self,
        auth_manager: AuthManager,
        crawler: CouponCrawler,
        logger: logging.Logger,
    ) -> None:
        self._auth_manager = auth_manager
        self._crawler = crawler
        self._logger = logger

    def run(self, force: bool = False) -> None:
        """执行一次完整的领券任务。force=True 时跳过时间窗口限制。"""
        task_time = datetime.now()
        self._logger.info(
            "任务开始，时间：%s", task_time.strftime("%Y-%m-%d %H:%M:%S")
        )

        try:
            # 步骤 1：检查凭证有效性
            if not self._auth_manager.is_valid():
                self._logger.error("凭证已失效，跳过本次领券任务")
                return

            # 步骤 2：注入 Cookie 到 crawler
            headers = self._auth_manager.get_headers()
            cookie = headers.get("Cookie", "")
            self._crawler.set_cookie(cookie)

            # 步骤 3：执行领券
            results = self._crawler.run(force=force)

            # 步骤 4：写入领券结果（供 Web 界面展示）
            try:
                from src.web.result_writer import write_result
                write_result(results, task_time)
            except Exception as exc:
                self._logger.warning("写入领券结果失败：%s", exc)

            # 步骤 5：记录任务完成日志
            from .models import ClaimStatus

            success_count = sum(1 for r in results if r.status == ClaimStatus.SUCCESS)
            failed_count = sum(1 for r in results if r.status == ClaimStatus.FAILED)
            skipped_count = sum(1 for r in results if r.status == ClaimStatus.SKIPPED)
            finish_time = datetime.now()
            self._logger.info(
                "任务完成，时间：%s，共 %d 张券（成功：%d，失败：%d，已领取：%d）",
                finish_time.strftime("%Y-%m-%d %H:%M:%S"),
                len(results),
                success_count,
                failed_count,
                skipped_count,
            )

        except CredentialInvalidError as exc:
            self._auth_manager.mark_invalid()
            self._logger.error("凭证失效：%s", exc)

        except CrawlerError as exc:
            self._logger.error("领券失败：%s", exc)

        except Exception as exc:
            self._logger.exception("任务执行时发生未预期异常：%s", exc)
