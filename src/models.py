"""
数据模型模块

包含：
- Pydantic 配置模型（用于配置文件校验）
- 运行时数据类（枚举、dataclass）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic 配置模型
# ---------------------------------------------------------------------------


class CredentialConfig(BaseModel):
    """京东账号凭证配置。"""

    cookie: str = Field(default="", description="京东账号 Cookie 字符串")


class CouponTargetConfig(BaseModel):
    """优惠券活动目标配置。"""

    url: str = Field(..., description="优惠券活动页面 URL")
    name: str = Field(default="", description="活动名称（可选，用于日志）")



class LogConfig(BaseModel):
    """日志配置。"""

    path: str = Field(default="logs/app.log", description="日志文件路径")
    max_bytes: int = Field(
        default=10 * 1024 * 1024, description="单文件最大字节数（默认 10 MB）"
    )
    backup_count: int = Field(default=7, description="保留归档文件数量")


class AppConfig(BaseModel):
    """应用全局配置。"""

    credential: CredentialConfig
    schedule: List[str] = Field(
        ...,
        min_length=1,
        description="cron 表达式列表，如 ['0 12 * * *']",
    )
    coupon_targets: List[CouponTargetConfig] = Field(
        ...,
        min_length=1,
        description="优惠券活动目标列表",
    )
    log: LogConfig = Field(default_factory=LogConfig)
    request_timeout: tuple[int, int] = Field(
        default=(5, 15),
        description="HTTP 超时 (connect_seconds, read_seconds)",
    )
    jd_area: str = Field(
        default="",
        description="京东收货地址编码，如 '17_1381_50713_62969'，影响可见券范围",
    )
    headless: bool = Field(
        default=False,
        description="是否以无头模式运行浏览器（False=弹出窗口，True=后台静默）",
    )
    grab_interval_ms: int = Field(
        default=300,
        description="抢券刷新间隔（毫秒），建议 100~2000，太快容易被风控",
    )


# ---------------------------------------------------------------------------
# 运行时数据模型
# ---------------------------------------------------------------------------


class ClaimStatus(str, Enum):
    """领券结果状态。"""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # 已领取


class FailReason(str, Enum):
    """领券失败原因。"""

    ALREADY_CLAIMED = "already_claimed"
    NOT_STARTED = "not_started"
    OUT_OF_STOCK = "out_of_stock"
    LOGIN_EXPIRED = "login_expired"
    HTTP_ERROR = "http_error"
    UNKNOWN = "unknown"


@dataclass
class CouponInfo:
    """优惠券基本信息。"""

    coupon_id: str
    name: str
    denomination: float  # 面额，单位：元
    min_spend: float  # 使用门槛，单位：元
    claim_url: str  # 领取接口 URL 或参数


@dataclass
class ClaimResult:
    """单张优惠券的领取结果。"""

    coupon_info: CouponInfo
    status: ClaimStatus
    fail_reason: FailReason | None = None
    claimed_at: datetime | None = None
