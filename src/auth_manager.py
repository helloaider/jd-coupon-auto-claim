"""
凭证管理模块

负责京东账号 Cookie 的加密存储、读取和有效性检测。
使用 Fernet 对称加密（AES-128-CBC + HMAC），密钥存储于独立文件。
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet

from src.models import CredentialConfig


# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------


class CredentialInvalidError(Exception):
    """凭证失效时抛出（如 Cookie 过期、未配置等）。"""


class KeyFileNotFoundError(Exception):
    """Fernet 密钥文件丢失时抛出。密钥丢失后已加密凭证无法解密，需重新配置。"""


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------


class AuthManager:
    """凭证管理器：负责加密存储、读取 Cookie，并跟踪凭证有效性。"""

    def __init__(
        self,
        config: CredentialConfig,
        store_path: str,
        key_path: str,
        logger: logging.Logger,
    ) -> None:
        self._config = config
        self._store_path = store_path
        self._key_path = key_path
        self._logger = logger
        self._valid: bool = True
        self._fernet: Fernet = self._load_or_create_key()

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _load_or_create_key(self) -> Fernet:
        """
        加载或创建 Fernet 密钥。

        - 若 key_path 文件存在，读取并返回 Fernet 实例。
        - 若不存在，生成新密钥，写入 key_path（确保目录存在），返回 Fernet 实例。

        注意：密钥文件一旦丢失，已加密的凭证无法解密，需重新配置。
        """
        if os.path.exists(self._key_path):
            with open(self._key_path, "rb") as f:
                key = f.read()
            return Fernet(key)

        # 生成新密钥并持久化
        key = Fernet.generate_key()
        key_dir = os.path.dirname(self._key_path)
        if key_dir:
            os.makedirs(key_dir, exist_ok=True)
        with open(self._key_path, "wb") as f:
            f.write(key)
        return Fernet(key)

    def _encrypt(self, plaintext: str) -> bytes:
        """用 Fernet 加密字符串，返回加密字节。"""
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def _decrypt(self, ciphertext: bytes) -> str:
        """用 Fernet 解密字节，返回原始字符串。"""
        return self._fernet.decrypt(ciphertext).decode("utf-8")

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        初始化凭证存储。

        - 若 config.cookie 非空，始终以新 cookie 覆盖加密存储（确保配置文件更新后生效）。
        - 若 config.cookie 为空且 store_path 文件已存在，使用已存储的加密凭证。
        - 若 config.cookie 为空且 store_path 文件不存在，抛出 CredentialInvalidError。
        日志中不记录 cookie 明文。
        """
        if self._config.cookie:
            # config.yaml 中有新 cookie，始终覆盖写入（保证更新立即生效）
            encrypted = self._encrypt(self._config.cookie)
            store_dir = os.path.dirname(self._store_path)
            if store_dir:
                os.makedirs(store_dir, exist_ok=True)
            with open(self._store_path, "wb") as f:
                f.write(encrypted)
            self._logger.info("凭证已从配置文件更新")
            return

        if os.path.exists(self._store_path):
            self._logger.info("使用已存储的加密凭证")
            return

        raise CredentialInvalidError(
            "凭证文件不存在且 config.yaml 中 cookie 为空，请先配置 cookie。"
        )

    def get_headers(self) -> dict[str, str]:
        """
        返回包含有效 Cookie 的 HTTP 请求头字典。

        若凭证已标记失效，抛出 CredentialInvalidError。
        日志中不记录 cookie 明文。
        """
        if not self._valid:
            raise CredentialInvalidError("凭证已失效，请重新配置 cookie。")

        with open(self._store_path, "rb") as f:
            ciphertext = f.read()
        cookie = self._decrypt(ciphertext)

        self._logger.info("注入凭证到请求头")
        return {
            "Cookie": cookie,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }

    def update_cookie(self, cookie: str) -> None:
        """
        用新 cookie 覆盖加密存储，并将凭证标记为有效。

        通常在浏览器登录后自动调用，无需手动拷贝 cookie。
        日志中不记录 cookie 明文。
        """
        encrypted = self._encrypt(cookie)
        store_dir = os.path.dirname(self._store_path)
        if store_dir:
            os.makedirs(store_dir, exist_ok=True)
        with open(self._store_path, "wb") as f:
            f.write(encrypted)
        self._valid = True
        self._logger.info("Cookie 已从浏览器自动更新并加密保存")

    def mark_invalid(self) -> None:
        """将内部 _valid 标志设为 False，记录日志。"""
        self._valid = False
        self._logger.warning("凭证已标记为失效")

    def is_valid(self) -> bool:
        """返回当前凭证是否有效。"""
        return self._valid
