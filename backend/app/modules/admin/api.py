from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.common.responses import success_response
from app.db.session import get_db
from app.repositories.ai_provider_config_repo import AIProviderConfigRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.user_repo import UserRepository
from app.services.admin_audit_service import AdminAuditService
from app.services.project_ai_config_service import ProjectAIConfigService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateProjectPayload(BaseModel):
    user_id: str | None = None
    name: str
    code: str | None = None
    status: str = "active"


class UpdateProjectPayload(BaseModel):
    name: str | None = None
    code: str | None = None
    status: str | None = None


class CreateAIConfigPayload(BaseModel):
    provider_type: str = "openai_compatible"
    base_url: str | None = None
    model: str
    api_key: str
    is_active: bool = True
    priority: int = 100
    remark: str | None = None


class UpdateAIConfigPayload(BaseModel):
    provider_type: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    is_active: bool | None = None
    priority: int | None = None
    remark: str | None = None


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), user=Depends(require_admin)) -> dict:
    users = await UserRepository(db).list_users()
    payload = [
        {
            "id": item.id,
            "username": item.username,
            "role": item.role,
            "is_active": item.is_active,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in users
    ]
    return success_response(payload)


@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db), user=Depends(require_admin)) -> dict:
    return success_response(await ProjectService(db).list_projects())


@router.post("/projects")
async def create_project(payload: CreateProjectPayload, db: AsyncSession = Depends(get_db), user=Depends(require_admin)) -> dict:
    created = await ProjectService(db).create_project(payload.model_dump())
    await AdminAuditService(db).log(
        admin_user_id=user.id,
        action="create_project",
        resource_type="project",
        resource_id=created["id"],
        payload=created,
    )
    await db.commit()
    return success_response(created, "project created")


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, payload: UpdateProjectPayload, db: AsyncSession = Depends(get_db), user=Depends(require_admin)) -> dict:
    updated = await ProjectService(db).update_project(project_id, payload.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="project not found")
    await AdminAuditService(db).log(
        admin_user_id=user.id,
        action="update_project",
        resource_type="project",
        resource_id=project_id,
        payload=payload.model_dump(exclude_none=True) | {"project_id": project_id},
    )
    await db.commit()
    return success_response(updated, "project updated")


@router.get("/projects/{project_id}/ai-configs")
async def list_ai_configs(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(require_admin)) -> dict:
    project = await ProjectRepository(db).get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return success_response(await ProjectAIConfigService(db).list_project_configs(project_id))


@router.post("/projects/{project_id}/ai-configs")
async def create_ai_config(project_id: str, payload: CreateAIConfigPayload, db: AsyncSession = Depends(get_db), user=Depends(require_admin)) -> dict:
    project = await ProjectRepository(db).get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    created = await ProjectAIConfigService(db).create_config(project_id, payload.model_dump(), admin_user_id=user.id)
    await AdminAuditService(db).log(
        admin_user_id=user.id,
        action="create_ai_config",
        resource_type="ai_provider_config",
        resource_id=created["id"],
        payload={"project_id": project_id, **created},
    )
    await db.commit()
    return success_response(created, "ai config created")


@router.patch("/ai-configs/{config_id}")
async def update_ai_config(config_id: str, payload: UpdateAIConfigPayload, db: AsyncSession = Depends(get_db), user=Depends(require_admin)) -> dict:
    updated = await ProjectAIConfigService(db).update_config(config_id, payload.model_dump(exclude_none=True), admin_user_id=user.id)
    if updated is None:
        raise HTTPException(status_code=404, detail="config not found")
    await AdminAuditService(db).log(
        admin_user_id=user.id,
        action="update_ai_config",
        resource_type="ai_provider_config",
        resource_id=config_id,
        payload={"config_id": config_id, **payload.model_dump(exclude_none=True), "project_id": updated["project_id"]},
    )
    await db.commit()
    return success_response(updated, "ai config updated")


@router.post("/ai-configs/{config_id}/test")
async def test_ai_config(config_id: str, db: AsyncSession = Depends(get_db), user=Depends(require_admin)) -> dict:
    configs = ProjectAIConfigService(db)
    config = await AIProviderConfigRepository(db).get_config(config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="config not found")
    result = await configs.test_config(config_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    await AdminAuditService(db).log(
        admin_user_id=user.id,
        action="test_ai_config",
        resource_type="ai_provider_config",
        resource_id=config_id,
        payload={"config_id": config_id, "project_id": config.project_id},
    )
    await db.commit()
    return success_response(result, "ai config test succeeded")


@router.get("/audit-logs")
async def list_audit_logs(
    project_id: str | None = Query(default=None),
    admin_user_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
) -> dict:
    return success_response(await AdminAuditService(db).list_logs(project_id=project_id, admin_user_id=admin_user_id))
