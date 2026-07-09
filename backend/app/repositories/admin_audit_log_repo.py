from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit_log import AdminAuditLog


class AdminAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_log(self, payload: dict) -> AdminAuditLog:
        record = AdminAuditLog(**payload)
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def list_logs(self, *, admin_user_id: str | None = None) -> list[AdminAuditLog]:
        query = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        if admin_user_id:
            query = query.where(AdminAuditLog.admin_user_id == admin_user_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())
