"""Basic Auth 中间件"""
import base64
import hmac
import os
import logging
from flask import request, Response

logger = logging.getLogger(__name__)


def check_auth(password: str, auth_header: str | None) -> bool:
    """使用常量时间比较校验 Basic Auth 凭证。

    解析 Authorization: Basic <base64> 头，base64 解码后格式为
    username:password（用户名任意，只校验密码部分）。
    使用 hmac.compare_digest 进行常量时间比较，防止时序侧信道泄露。
    """
    if not auth_header:
        return False

    # 期望格式：Basic <base64编码的 username:password>
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "basic":
        return False

    try:
        decoded = base64.b64decode(parts[1]).decode("utf-8")
    except Exception:
        return False

    # 格式为 username:password，用户名任意，只校验密码
    if ":" not in decoded:
        return False

    _, provided_password = decoded.split(":", 1)

    # 使用常量时间比较，防止时序侧信道泄露
    return hmac.compare_digest(provided_password, password)


def require_auth() -> Response | None:
    """Flask before_request 钩子：校验 Basic Auth。

    - 若未设置 WEB_PASSWORD 环境变量，直接放行
    - 若请求路径以 /static/ 开头，直接放行
    - 若请求路径为 /，直接放行（Dashboard 主页）
    - 否则校验 Authorization 头，失败时返回 HTTP 401
    """
    password = os.environ.get("WEB_PASSWORD")

    # 未设置密码，放行所有请求
    if not password:
        return None

    # 静态资源路径，放行
    if request.path.startswith("/static/"):
        return None

    # Dashboard 主页，放行
    if request.path == "/":
        return None

    # 校验 Basic Auth
    auth_header = request.headers.get("Authorization")
    if check_auth(password, auth_header):
        return None

    # 认证失败，返回 401
    return Response(
        "Unauthorized",
        status=401,
        headers={"WWW-Authenticate": 'Basic realm="JD Coupon Manager"'},
    )


def init_auth(app) -> None:
    """注册 before_request 钩子到 Flask app。

    若 WEB_PASSWORD 未设置，打印警告提示用户界面无认证保护。
    """
    if not os.environ.get("WEB_PASSWORD"):
        logger.warning("未设置 WEB_PASSWORD，Web 界面无认证保护")

    app.before_request(require_auth)
