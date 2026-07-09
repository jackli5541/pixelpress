from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, verify_password
from app.auth.security import create_access_token
from app.repositories.user_repo import UserRepository


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)

    async def register(self, username: str, password: str, role: str = "user") -> dict | None:
        existing = await self.user_repo.get_by_username(username)
        if existing is not None:
            return None
        normalized_role = "user" if role != "admin" else "user"
        user = await self.user_repo.create_user(
            {
                "username": username,
                "password_hash": hash_password(password),
                "role": normalized_role,
                "is_active": True,
            }
        )
        await self.session.commit()
        return {"id": user.id, "username": user.username, "role": user.role}

    async def create_admin_user(self, username: str, password: str) -> dict | None:
        existing = await self.user_repo.get_by_username(username)
        if existing is not None:
            return None
        user = await self.user_repo.create_user(
            {
                "username": username,
                "password_hash": hash_password(password),
                "role": "admin",
                "is_active": True,
            }
        )
        await self.session.commit()
        return {"id": user.id, "username": user.username, "role": user.role}

    async def login(self, username: str, password: str) -> dict | None:
        user = await self.user_repo.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            return None
        token = create_access_token(user.username, user.role)
        return {"access_token": token, "token_type": "bearer", "role": user.role, "username": user.username}
