from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def list_users(self) -> list[User]:
        result = await self.session.execute(select(User).order_by(User.created_at, User.id))
        return list(result.scalars().all())

    async def create_user(self, payload: dict) -> User:
        user = User(**payload)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user
