from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings


class SecretService:
    @staticmethod
    def _build_fernet() -> Fernet:
        settings = get_settings()
        if settings.is_production:
            if not settings.secrets_master_key:
                raise RuntimeError("SECRETS_MASTER_KEY is required in production")
            master_key = settings.secrets_master_key
        else:
            master_key = settings.secrets_master_key or settings.auth_secret_key
        digest = hashlib.sha256(master_key.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def encrypt_text(self, plain_text: str) -> str:
        return self._build_fernet().encrypt(plain_text.encode("utf-8")).decode("utf-8")

    def decrypt_text(self, cipher_text: str) -> str:
        return self._build_fernet().decrypt(cipher_text.encode("utf-8")).decode("utf-8")

    def encrypt_api_key(self, plain_text: str) -> str:
        return self.encrypt_text(plain_text)

    def decrypt_api_key(self, cipher_text: str) -> str:
        return self.decrypt_text(cipher_text)

    @staticmethod
    def mask_api_key(plain_text: str) -> str:
        if len(plain_text) <= 8:
            return "*" * len(plain_text)
        return f"{plain_text[:4]}****{plain_text[-4:]}"
