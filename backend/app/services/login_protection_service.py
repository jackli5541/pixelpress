from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings


class LoginProtectionError(RuntimeError):
    pass


class LoginProtectionService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = Redis.from_url(self.settings.redis_url, decode_responses=True)

    @staticmethod
    def _user_fail_key(username: str) -> str:
        return f"login_fail:user:{username}"

    @staticmethod
    def _ip_fail_key(client_ip: str) -> str:
        return f"login_fail:ip:{client_ip}"

    @staticmethod
    def _user_lock_key(username: str) -> str:
        return f"login_lock:user:{username}"

    @staticmethod
    def _ip_lock_key(client_ip: str) -> str:
        return f"login_lock:ip:{client_ip}"

    async def check_login_allowed(self, username: str, client_ip: str) -> None:
        if await self.redis.exists(self._user_lock_key(username)):
            raise LoginProtectionError("too many login attempts, please try again later")
        if await self.redis.exists(self._ip_lock_key(client_ip)):
            raise LoginProtectionError("too many login attempts, please try again later")

    async def record_login_failure(self, username: str, client_ip: str) -> None:
        window = self.settings.auth_login_attempt_window_seconds
        lockout = self.settings.auth_login_lockout_seconds
        threshold = self.settings.auth_login_max_failures

        user_fail_key = self._user_fail_key(username)
        ip_fail_key = self._ip_fail_key(client_ip)
        user_count = await self.redis.incr(user_fail_key)
        ip_count = await self.redis.incr(ip_fail_key)
        await self.redis.expire(user_fail_key, window)
        await self.redis.expire(ip_fail_key, window)

        if user_count >= threshold:
            await self.redis.set(self._user_lock_key(username), "1", ex=lockout)
        if ip_count >= threshold:
            await self.redis.set(self._ip_lock_key(client_ip), "1", ex=lockout)

    async def clear_login_failures(self, username: str, client_ip: str) -> None:
        await self.redis.delete(self._user_fail_key(username), self._ip_fail_key(client_ip))
