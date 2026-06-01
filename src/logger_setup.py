"""
日志初始化模块

提供 setup_logger() 函数，基于 LogConfig 配置创建带有
RotatingFileHandler 和 StreamHandler 的 Logger 实例。
"""

import logging
import logging.handlers
import os
from pathlib import Path

from src.models import LogConfig

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(config: LogConfig, name: str = "jd_coupon") -> logging.Logger:
    """
    初始化并返回一个配置好的 Logger 实例。

    - 日志级别：INFO
    - 同时输出到文件（RotatingFileHandler）和控制台（StreamHandler）
    - 日志目录不存在时自动创建
    - 避免重复添加 handler

    Args:
        config: LogConfig 实例，包含日志文件路径、最大字节数和备份数量。
        name:   Logger 名称，默认为 "jd_coupon"。

    Returns:
        配置好的 logging.Logger 实例。
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # 使用 pathlib.Path 处理路径，兼容 Windows
    log_path = Path(config.path)
    log_dir = log_path.parent
    os.makedirs(log_dir, exist_ok=True)

    # 文件 handler（滚动归档）
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path,
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
