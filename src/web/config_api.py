"""
配置管理 API 模块

提供 GET /api/config 和 POST /api/config 两个端点，
用于读取和保存 config.yaml 配置文件。
"""

from __future__ import annotations

import os
import tempfile

import yaml
from apscheduler.triggers.cron import CronTrigger
from flask import Blueprint, current_app, jsonify, request

from src.config_loader import ConfigLoader

config_bp = Blueprint("config", __name__)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def mask_sensitive(value: str, keep: int = 8) -> str:
    """
    对敏感字符串做掩码处理。

    若 value 长度 <= keep，返回原值（不掩码）；
    否则返回 value[:keep] + "****"。
    """
    if len(value) <= keep:
        return value
    return value[:keep] + "****"


def is_masked(value: str) -> bool:
    """返回 value 是否包含 '****'（即已被掩码处理）。"""
    return "****" in value


def validate_cron(cron: str) -> bool:
    """
    校验 cron 表达式是否合法。

    使用 CronTrigger.from_crontab() 尝试解析，成功返回 True，抛出异常返回 False。
    """
    try:
        CronTrigger.from_crontab(cron)
        return True
    except Exception:
        return False


def validate_url(url: str) -> bool:
    """返回 url 是否以 'http://' 或 'https://' 开头。"""
    return url.startswith("http://") or url.startswith("https://")


def atomic_write_yaml(path: str, data: dict) -> None:
    """
    原子写入 YAML 文件。

    先写入同目录的临时文件，成功后使用 os.replace() 原子替换目标文件，
    防止写入中途崩溃导致文件损坏。
    """
    dir_ = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        os.replace(tmp_path, path)
    except Exception:
        # 清理临时文件，重新抛出异常
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# 空配置模板（config.yaml 不存在时返回）
# ---------------------------------------------------------------------------

_EMPTY_CONFIG_TEMPLATE = {
    "credential": {"cookie": ""},
    "schedule": [],
    "coupon_targets": [],
    "jd_area": "",
    "headless": False,
    "log": {
        "path": "logs/app.log",
        "max_bytes": 10485760,
        "backup_count": 7,
    },
}


# ---------------------------------------------------------------------------
# GET /api/config
# ---------------------------------------------------------------------------


@config_bp.route("/api/config", methods=["GET"])
def get_config():
    """
    读取当前配置，对敏感字段做掩码处理后返回 JSON。

    若 config.yaml 不存在，返回空配置模板（所有字段为默认值）。
    """
    config_path = current_app.config["CONFIG_PATH"]

    if not os.path.exists(config_path):
        return jsonify(_EMPTY_CONFIG_TEMPLATE), 200

    try:
        app_config = ConfigLoader().load(config_path)
    except Exception as exc:
        return jsonify({"error": "config_load_error", "message": str(exc)}), 500

    # 将 AppConfig 转换为字典
    config_dict = app_config.model_dump()

    # 对敏感字段做掩码处理
    # credential.cookie
    cookie = config_dict.get("credential", {}).get("cookie", "")
    if cookie:
        config_dict["credential"]["cookie"] = mask_sensitive(cookie)

    return jsonify(config_dict), 200


# ---------------------------------------------------------------------------
# POST /api/config
# ---------------------------------------------------------------------------


@config_bp.route("/api/config", methods=["POST"])
def post_config():
    """
    保存配置到 config.yaml。

    校验 cron 表达式和 URL 格式，若 Cookie 字段包含掩码则保留原始值，
    使用原子写入防止 I/O 错误破坏原文件。
    """
    config_path = current_app.config["CONFIG_PATH"]
    data = request.get_json(force=True, silent=True)

    if data is None:
        return (
            jsonify(
                {
                    "error": "invalid_json",
                    "message": "请求体必须是合法的 JSON",
                    "detail": "",
                }
            ),
            400,
        )

    # 校验 schedule 中的 cron 表达式
    schedules = data.get("schedule", [])
    if isinstance(schedules, list):
        for cron in schedules:
            if isinstance(cron, str) and not validate_cron(cron):
                return (
                    jsonify(
                        {
                            "error": "invalid_cron",
                            "message": f"非法的 cron 表达式：{cron}",
                            "detail": f"非法的 cron 表达式：{cron}",
                        }
                    ),
                    400,
                )

    # 校验 coupon_targets 中的 URL
    coupon_targets = data.get("coupon_targets", [])
    if isinstance(coupon_targets, list):
        for target in coupon_targets:
            url = target.get("url", "") if isinstance(target, dict) else ""
            if url and not validate_url(url):
                return (
                    jsonify(
                        {
                            "error": "invalid_url",
                            "message": f"非法的 URL：{url}",
                            "detail": f"非法的 URL：{url}",
                        }
                    ),
                    400,
                )

    # 若 credential.cookie 包含掩码，从现有 config.yaml 读取原始 cookie 保留
    credential = data.get("credential", {})
    if isinstance(credential, dict):
        cookie_value = credential.get("cookie", "")
        if isinstance(cookie_value, str) and is_masked(cookie_value):
            # 尝试从现有配置文件读取原始 cookie
            if os.path.exists(config_path):
                try:
                    existing_config = ConfigLoader().load(config_path)
                    data["credential"]["cookie"] = existing_config.credential.cookie
                except Exception:
                    # 无法读取原始配置，保留掩码值（不覆盖）
                    pass

    # 原子写入 config.yaml
    try:
        atomic_write_yaml(config_path, data)
    except OSError as exc:
        return (
            jsonify(
                {
                    "error": "io_error",
                    "message": f"配置文件写入失败：{exc}",
                    "detail": str(exc),
                }
            ),
            500,
        )
    except Exception as exc:
        return (
            jsonify(
                {
                    "error": "write_error",
                    "message": f"配置保存失败：{exc}",
                    "detail": str(exc),
                }
            ),
            500,
        )

    return jsonify({"message": "配置保存成功"}), 200
