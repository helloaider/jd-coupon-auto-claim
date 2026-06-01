"""领券结果写入器"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime

from src.models import ClaimResult, ClaimStatus

# 最多保留的历史记录条数
_MAX_HISTORY = 50


def write_result(
    results: list[ClaimResult],
    task_time: datetime,
    path: str = "data/last_result.json",
) -> None:
    """将领券结果序列化为 JSON 原子写入文件，保留历史记录。

    Args:
        results: 本次任务的领券结果列表。
        task_time: 任务执行时间。
        path: 输出文件路径，默认为 data/last_result.json。
    """
    success_count = sum(1 for r in results if r.status == ClaimStatus.SUCCESS)
    failed_count = sum(1 for r in results if r.status == ClaimStatus.FAILED)
    skipped_count = sum(1 for r in results if r.status == ClaimStatus.SKIPPED)

    items = []
    for r in results:
        items.append(
            {
                "coupon_id": r.coupon_info.coupon_id,
                "name": r.coupon_info.name,
                "denomination": r.coupon_info.denomination,
                "min_spend": r.coupon_info.min_spend,
                "status": r.status.value,
                "fail_reason": r.fail_reason.value if r.fail_reason is not None else None,
                "claimed_at": r.claimed_at.isoformat() if r.claimed_at is not None else None,
            }
        )

    new_entry = {
        "schema_version": 1,
        "executed_at": task_time.isoformat(),
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
        },
        "items": items,
    }

    # 确保目标目录存在
    dir_ = os.path.dirname(os.path.abspath(path))
    os.makedirs(dir_, exist_ok=True)

    # 读取已有历史记录
    history: list[dict] = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            # 兼容旧格式（单条记录）和新格式（history 列表）
            if isinstance(existing, dict) and "history" in existing:
                history = existing["history"]
            elif isinstance(existing, dict) and "executed_at" in existing:
                # 旧格式单条，迁移为列表
                history = [existing]
        except Exception:
            history = []

    # 新记录插入最前面，并限制最大条数
    history.insert(0, new_entry)
    if len(history) > _MAX_HISTORY:
        history = history[:_MAX_HISTORY]

    data = {
        "schema_version": 2,
        "latest": new_entry,
        "history": history,
    }

    # 原子写入：先写临时文件，再 os.replace()
    with tempfile.NamedTemporaryFile(
        "w",
        dir=dir_,
        delete=False,
        encoding="utf-8",
        suffix=".tmp",
    ) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path = f.name

    os.replace(tmp_path, path)
