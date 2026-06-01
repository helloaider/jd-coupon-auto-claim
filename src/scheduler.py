"""
调度器模块

封装 APScheduler，管理定时任务的注册和生命周期。
- blocking=True（默认）：BlockingScheduler，在主线程执行任务，与 Playwright 同线程
- blocking=False：BackgroundScheduler，在后台线程执行，供 Web 模式使用
"""

from __future__ import annotations

import logging
from typing import Callable

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.triggers.cron import CronTrigger


class Scheduler:
    """APScheduler 封装，管理 cron 触发的领券任务。"""

    def __init__(
        self,
        schedule: list[str],
        task_runner_func: Callable,
        logger: logging.Logger,
        blocking: bool = True,
    ) -> None:
        self._schedule = schedule
        self._task_runner_func = task_runner_func
        self._logger = logger
        self._blocking = blocking

        if blocking:
            from apscheduler.schedulers.blocking import BlockingScheduler
            self._scheduler = BlockingScheduler(
                job_defaults={
                    "misfire_grace_time": 60,
                    "coalesce": True,
                    "max_instances": 1,
                },
            )
        else:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.executors.pool import ThreadPoolExecutor
            self._scheduler = BackgroundScheduler(
                executors={"default": ThreadPoolExecutor(max_workers=1)},
                job_defaults={
                    "misfire_grace_time": 60,
                    "coalesce": True,
                    "max_instances": 1,
                },
            )

        self._scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)
        self._scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)

    def _register_jobs(self) -> None:
        for i, cron in enumerate(self._schedule):
            trigger = CronTrigger.from_crontab(cron)
            self._scheduler.add_job(
                self._task_runner_func,
                trigger,
                id=f"coupon_task_{i}",
                name=f"领券任务 {i + 1}",
            )
            self._logger.info("已注册领券任务，cron：%s", cron)

    def start(self) -> None:
        """启动调度器。blocking 模式下阻塞主线程，非 blocking 模式下立即返回。"""
        self._register_jobs()
        self._logger.info("调度器已启动，等待触发时间...")
        try:
            self._scheduler.start()  # blocking 模式会阻塞，background 模式立即返回
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            self._logger.info("调度器已停止")

    def _on_job_missed(self, event) -> None:
        self._logger.warning("任务错过，job_id：%s", event.job_id)

    def _on_job_error(self, event) -> None:
        self._logger.error("任务执行出错，job_id：%s，异常：%s", event.job_id, event.exception)

    def get_job_count(self) -> int:
        return len(self._scheduler.get_jobs())
