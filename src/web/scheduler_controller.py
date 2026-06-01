"""
调度器控制器（子进程模式）

通过 subprocess 启动独立的 worker.py 进程来运行 Playwright + 调度器，
避免 Playwright 的 greenlet 跨线程限制。
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading

from flask import Blueprint, current_app, jsonify

scheduler_bp = Blueprint("scheduler", __name__)


def _get_worker_cmd(config_path: str, run_now: bool = False, once: bool = False) -> list[str]:
    """构造启动 worker 的命令。打包为 exe 时用 sys.executable + worker 参数。"""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        cmd = [exe, "--worker", "--config", config_path]
    else:
        cmd = [sys.executable, "worker.py", "--config", config_path]
    if run_now:
        cmd.append("--run-now")
    if once:
        cmd.append("--once")
    return cmd


class SchedulerController:
    """通过子进程管理抢券工作进程的生命周期。"""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._logger = logging.getLogger(__name__)

    def start(self, config_path: str) -> tuple[bool, str]:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return False, "任务已在运行中"

            cmd = _get_worker_cmd(config_path)
            self._logger.info("启动工作进程：%s", " ".join(cmd))
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=os.getcwd(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except Exception as exc:
                return False, f"启动失败：{exc}"

            # 后台线程读取子进程输出写入日志
            threading.Thread(
                target=self._pipe_output,
                args=(self._proc,),
                daemon=True,
            ).start()

            return True, "任务已启动"

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = None
                return False, "任务未在运行"
            try:
                # 写退出标志文件，让 worker 主循环优雅退出并关闭浏览器
                stop_flag = os.path.join(os.getcwd(), "data", ".stop_worker")
                try:
                    with open(stop_flag, "w") as f:
                        f.write("stop")
                except Exception:
                    pass
                # 等待 worker 自行退出（最多 10 秒）
                try:
                    self._proc.wait(timeout=10)
                except Exception:
                    pass
                # 若还未退出则强杀
                if self._proc.poll() is None:
                    try:
                        self._proc.kill()
                        self._proc.wait(timeout=3)
                    except Exception:
                        pass
                # 清理标志文件
                try:
                    os.remove(stop_flag)
                except Exception:
                    pass
            finally:
                self._proc = None
            return True, "任务已停止"

    def run_now(self, config_path: str) -> tuple[bool, str]:
        """启动一个临时子进程立即执行一次，执行完自动退出，不影响正在运行的调度器。"""
        cmd = _get_worker_cmd(config_path, once=True)
        self._logger.info("立即执行：%s", " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            threading.Thread(
                target=self._pipe_output,
                args=(proc,),
                daemon=True,
            ).start()
        except Exception as exc:
            return False, f"启动失败：{exc}"
        return True, "任务已触发，正在后台执行"

    def get_status(self) -> dict:
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            return {"running": running, "next_run_times": [], "job_count": 0}

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def _pipe_output(self, proc: subprocess.Popen) -> None:
        """把子进程的 stdout 转发到日志。"""
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self._logger.info("[worker] %s", line)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Flask Blueprint 端点
# ---------------------------------------------------------------------------

def _get_controller() -> SchedulerController:
    return current_app.extensions["scheduler_controller"]


@scheduler_bp.route("/api/scheduler/status", methods=["GET"])
def get_status():
    return jsonify(_get_controller().get_status()), 200


@scheduler_bp.route("/api/scheduler/start", methods=["POST"])
def start_scheduler():
    controller = _get_controller()
    config_path = current_app.config.get("CONFIG_PATH", "config.yaml")
    success, message = controller.start(config_path)
    if success:
        return jsonify({"message": message}), 200
    return jsonify({"error": "conflict", "message": message}), 409


@scheduler_bp.route("/api/scheduler/stop", methods=["POST"])
def stop_scheduler():
    controller = _get_controller()
    success, message = controller.stop()
    if success:
        return jsonify({"message": message}), 200
    return jsonify({"error": "conflict", "message": message}), 409


@scheduler_bp.route("/api/scheduler/run-now", methods=["POST"])
def run_now():
    controller = _get_controller()
    config_path = current_app.config.get("CONFIG_PATH", "config.yaml")
    success, message = controller.run_now(config_path)
    if success:
        return jsonify({"message": message}), 200
    return jsonify({"error": "bad_request", "message": message}), 400
