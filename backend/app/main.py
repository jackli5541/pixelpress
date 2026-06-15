from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.common.responses import success_response
from app.storage.file_store import get_uploads_root

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI 相册书自动排版系统后端骨架",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=get_uploads_root()), name="uploads")


@app.get("/")
def root() -> dict:
    return success_response(
        {
            "app": settings.app_name,
            "env": settings.app_env,
        }
    )


app.include_router(api_router)
