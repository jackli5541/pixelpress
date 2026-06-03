from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from pixelpress_backend.api.router import api_router
from pixelpress_backend.core.config import settings
from pixelpress_backend.services.exceptions import ConflictError, InvalidStateError, NotFoundError


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.exception_handler(ConflictError)
    async def handle_conflict(_: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"error_code": "CONFLICT", "message": str(exc)})

    @app.exception_handler(NotFoundError)
    async def handle_not_found(_: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"error_code": "NOT_FOUND", "message": str(exc)})

    @app.exception_handler(InvalidStateError)
    async def handle_invalid_state(_: Request, exc: InvalidStateError):
        return JSONResponse(status_code=400, content={"error_code": "INVALID_STATE", "message": str(exc)})

    return app


app = create_app()
