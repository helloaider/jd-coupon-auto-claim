"""
配置加载器模块

负责从 YAML 或 JSON 文件加载配置，并通过 Pydantic 校验返回 AppConfig。
"""

from __future__ import annotations

import json
import os
from typing import Literal

from pydantic import ValidationError

from src.models import AppConfig


class ConfigValidationError(Exception):
    """配置校验错误，包含出错字段名称和原因。"""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"字段 '{field}': {reason}")


class ConfigLoader:
    """从文件加载并校验应用配置。"""

    def load(self, path: str) -> AppConfig:
        """
        加载 YAML 或 JSON 配置文件，返回校验后的 AppConfig。

        若文件不存在、格式错误或必填字段缺失/非法，抛出 ConfigValidationError，
        错误信息包含字段名和具体原因。
        """
        if not os.path.exists(path):
            raise ConfigValidationError(path, "文件不存在")

        fmt = self._detect_format(path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                if fmt == "yaml":
                    try:
                        import yaml  # type: ignore
                    except ImportError as exc:
                        raise ConfigValidationError(
                            path, "缺少 PyYAML 依赖，请执行 pip install pyyaml"
                        ) from exc
                    raw = yaml.safe_load(f)
                else:
                    raw = json.load(f)
        except ConfigValidationError:
            raise
        except Exception as exc:
            raise ConfigValidationError(path, f"文件解析失败：{exc}") from exc

        if not isinstance(raw, dict):
            raise ConfigValidationError(path, "配置文件顶层必须是一个映射（dict）")

        return self._validate(raw)

    def _detect_format(self, path: str) -> Literal["yaml", "json"]:
        """
        根据文件扩展名检测格式。

        .yaml / .yml → yaml
        .json        → json
        其他          → 抛出 ConfigValidationError
        """
        _, ext = os.path.splitext(path)
        ext = ext.lower()
        if ext in (".yaml", ".yml"):
            return "yaml"
        if ext == ".json":
            return "json"
        raise ConfigValidationError(
            path,
            f"不支持的文件扩展名 '{ext}'，仅支持 .yaml / .yml / .json",
        )

    def _validate(self, raw: dict) -> AppConfig:
        """
        用 Pydantic 校验 raw dict，捕获 ValidationError 并转换为 ConfigValidationError。

        错误信息格式：字段 '{field}': {message}
        """
        try:
            return AppConfig.model_validate(raw)
        except ValidationError as exc:
            # 取第一个错误，转换为 ConfigValidationError
            first_error = exc.errors()[0]
            # loc 是字段路径元组，如 ('credential', 'cookie')
            loc = first_error.get("loc", ())
            field = ".".join(str(part) for part in loc) if loc else "unknown"
            message = first_error.get("msg", str(exc))
            raise ConfigValidationError(field, message) from exc
