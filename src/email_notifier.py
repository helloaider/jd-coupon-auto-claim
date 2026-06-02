"""
QQ 邮箱通知模块

在领券任务完成后发送结果通知邮件。
仅支持 QQ 邮箱（smtp.qq.com:465 SSL），使用授权码认证。
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime

from src.models import ClaimResult, ClaimStatus, EmailNotifyConfig


_SMTP_HOST = "smtp.qq.com"
_SMTP_PORT = 465


def send_result_email(
    cfg: EmailNotifyConfig,
    results: list[ClaimResult],
    task_time: datetime,
    logger: logging.Logger,
) -> None:
    """
    发送领券结果通知邮件。

    Args:
        cfg: QQ 邮箱配置（qq、auth_code、receiver）
        results: 本次任务的领券结果列表
        task_time: 任务执行时间
        logger: 日志记录器
    """
    if not cfg.qq or not cfg.auth_code:
        logger.warning("邮件通知：QQ 号或授权码未配置，跳过发送")
        return

    sender = f"{cfg.qq}@qq.com"
    receiver = cfg.receiver.strip() if cfg.receiver.strip() else sender

    # 统计
    success = sum(1 for r in results if r.status == ClaimStatus.SUCCESS)
    failed  = sum(1 for r in results if r.status == ClaimStatus.FAILED)
    skipped = sum(1 for r in results if r.status == ClaimStatus.SKIPPED)
    total   = len(results)

    # 标题
    if success > 0:
        subject = f"✅ 抢券成功 {success} 张 — 京东外卖优惠券助手"
    elif total == 0:
        subject = "ℹ️ 领券任务完成（无结果） — 京东外卖优惠券助手"
    else:
        subject = f"❌ 未抢到券 — 京东外卖优惠券助手"

    # 正文（纯文本）
    time_str = task_time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"京东外卖优惠券抢券结果",
        f"执行时间：{time_str}",
        f"",
        f"汇总：共 {total} 张  成功 {success}  失败 {failed}  已领取 {skipped}",
        f"",
    ]

    if results:
        lines.append("明细：")
        for r in results:
            status_str = {"success": "✅ 成功", "failed": "❌ 失败", "skipped": "⏭ 已领取"}.get(
                r.status.value, r.status.value
            )
            name = r.coupon_info.name or "未知券"
            reason = f"（{r.fail_reason.value}）" if r.fail_reason else ""
            claimed = r.claimed_at.strftime("%H:%M:%S") if r.claimed_at else ""
            lines.append(f"  {name}  {status_str}{reason}  {claimed}")
    else:
        lines.append("本次任务无券详情。")

    lines += ["", "— 由京东外卖定时优惠券抢券助手自动发送"]
    body = "\n".join(lines)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("京东外卖抢券助手", sender))
    msg["To"] = receiver

    try:
        with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, timeout=15) as smtp:
            smtp.login(sender, cfg.auth_code)
            smtp.sendmail(sender, [receiver], msg.as_string())
        logger.info("邮件通知已发送至 %s", receiver)
    except smtplib.SMTPAuthenticationError:
        logger.error("邮件通知：授权码错误或未开启 SMTP 服务，发送失败")
    except smtplib.SMTPException as exc:
        logger.error("邮件通知：SMTP 错误：%s", exc)
    except Exception as exc:
        logger.error("邮件通知：发送失败：%s", exc)
