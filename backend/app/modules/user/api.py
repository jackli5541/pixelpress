from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.rate_limit import limiter
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.db.session import get_db
from app.services.auth_service import AuthService
from app.services.login_protection_service import LoginProtectionError, LoginProtectionService
from app.services.project_service import ProjectService

router = APIRouter(tags=["users"])
users_router = APIRouter(prefix="/users", tags=["users"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterPayload(BaseModel):
    username: str
    password: str


class LoginPayload(BaseModel):
    username: str
    password: str


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@auth_router.post("/register")
@limiter.limit(get_settings().rate_limit_register, key_func=get_remote_address)
async def register(request: Request, payload: RegisterPayload, db: AsyncSession = Depends(get_db)) -> dict:
    user = await AuthService(db).register(payload.username, payload.password, "user")
    if user is None:
        raise HTTPException(status_code=400, detail="username already exists")
    return success_response(user, "register success")


@auth_router.post("/login")
@limiter.limit(get_settings().rate_limit_login, key_func=get_remote_address)
async def login(request: Request, payload: LoginPayload, db: AsyncSession = Depends(get_db)) -> dict:
    protection = LoginProtectionService()
    client_ip = _client_ip(request)
    try:
        await protection.check_login_allowed(payload.username, client_ip)
    except LoginProtectionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    token = await AuthService(db).login(payload.username, payload.password)
    if token is None:
        await protection.record_login_failure(payload.username, client_ip)
        raise HTTPException(status_code=401, detail="invalid credentials")

    await protection.clear_login_failures(payload.username, client_ip)
    return success_response(token, "login success")


@users_router.get("/me")
async def me(user=Depends(get_current_user)) -> dict:
    return success_response(
        {
            "authenticated": True,
            "role": user.role,
            "username": user.username,
            "id": user.id,
        }
    )


@users_router.get("/me/projects")
async def my_projects(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    projects = await ProjectService(db).list_user_projects(user.id, ensure_default=True)
    return success_response(projects)


@users_router.delete("/me/projects/{project_id}")
async def delete_my_project(project_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    raise HTTPException(status_code=409, detail="projects are managed by administrators")
