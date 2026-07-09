from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.admin_audit_log_repo import AdminAuditLogRepository


class AdminAuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AdminAuditLogRepository(session)

    async def log(self, *, admin_user_id: str | None, action: str, resource_type: str, resource_id: str, payload: dict | None = None):
        return await self.repo.create_log(
            {
                "admin_user_id": admin_user_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "payload_json": payload or {},
            }
        )

    async def list_logs(self, *, project_id: str | None = None, admin_user_id: str | None = None) -> list[dict]:
        records = await self.repo.list_logs(admin_user_id=admin_user_id)
        payload = [
            {
                "id": item.id,
                "admin_user_id": item.admin_user_id,
                "action": item.action,
                "resource_type": item.resource_type,
                "resource_id": item.resource_id,
                "payload": item.payload_json,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in records
        ]
        if project_id:
            payload = [item for item in payload if (item.get("payload") or {}).get("project_id") == project_id]
        return payload
