"""日志读取器"""
from __future__ import annotations

import os

from flask import Blueprint, jsonify
from flask import request as flask_request


def read_last_lines(path: str, n: int = 200) -> list[str]:
    """高效读取日志文件最后 N 行（从文件末尾反向扫描）。

    Args:
        path: 日志文件路径。
        n: 读取的最大行数，默认 200。

    Returns:
        最后 n 行的列表（顺序：从旧到新），每行已去掉末尾换行符。
        文件不存在时返回空列表。
    """
    if not os.path.exists(path):
        return []

    with open(path, "rb") as f:
        # 移动到文件末尾，获取文件大小
        f.seek(0, 2)
        file_size = f.tell()

        if file_size == 0:
            return []

        # 从末尾反向扫描，收集足够的行
        chunk_size = 8192
        lines_found: list[bytes] = []
        remaining = file_size
        leftover = b""

        while remaining > 0 and len(lines_found) <= n:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            chunk = f.read(read_size)

            # 将 leftover（上一次扫描的头部）拼接到当前块末尾
            chunk = chunk + leftover

            # 按换行符分割
            parts = chunk.split(b"\n")

            # parts[-1] 是当前块的头部（可能不完整），留作下次 leftover
            leftover = parts[0]
            # parts[1:] 是完整行（倒序）
            lines_found = parts[1:] + lines_found

        # 处理最后剩余的 leftover（文件开头部分）
        if leftover:
            lines_found = [leftover] + lines_found

        # 取最后 n 行
        last_n = lines_found[-n:] if len(lines_found) > n else lines_found

    # 解码并去掉末尾换行符
    result = []
    for line in last_n:
        decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
        result.append(decoded)

    return result


def clear_log(path: str) -> None:
    """清空日志文件内容（保留文件）。

    Args:
        path: 日志文件路径。若文件不存在则不做任何操作。
    """
    if not os.path.exists(path):
        return
    with open(path, "w", encoding="utf-8"):
        pass


# ---------------------------------------------------------------------------
# Flask Blueprint
# ---------------------------------------------------------------------------

log_bp = Blueprint("log", __name__)


@log_bp.route("/api/logs", methods=["GET"])
def get_logs():
    """读取最新 N 行日志。"""
    lines_param = flask_request.args.get("lines", 200, type=int)
    lines = read_last_lines("logs/app.log", n=lines_param)
    return jsonify({"lines": lines, "total": len(lines)}), 200


@log_bp.route("/api/logs", methods=["DELETE"])
def delete_logs():
    """清空日志文件。"""
    clear_log("logs/app.log")
    return jsonify({"message": "日志已清空"}), 200
