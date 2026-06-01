"""领券结果 API"""
from __future__ import annotations

import json
import os

from flask import Blueprint, jsonify

result_bp = Blueprint("result", __name__)


@result_bp.route("/api/result", methods=["GET"])
def get_result():
    """读取最近一次领券结果及历史记录。"""
    path = "data/last_result.json"
    if not os.path.exists(path):
        return jsonify({"result": None, "history": []}), 200
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 兼容旧格式（schema_version=1，单条记录）
    if data.get("schema_version", 1) < 2:
        return jsonify({"result": data, "history": [data]}), 200

    return jsonify({
        "result": data.get("latest"),
        "history": data.get("history", []),
    }), 200
