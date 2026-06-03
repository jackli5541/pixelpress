from fastapi import APIRouter, Depends

from pixelpress_backend.api.dependencies import get_layout_service
from pixelpress_backend.models.domain import GenerateLayoutRequest, LayoutGenerateResponse, TaskStatusResponse
from pixelpress_backend.services.layout_service import LayoutService


router = APIRouter(prefix="/layouts", tags=["layouts"])


@router.post("/generate", response_model=LayoutGenerateResponse)
def generate_layout(
    request: GenerateLayoutRequest,
    service: LayoutService = Depends(get_layout_service),
):
    return service.generate_layout(request)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(
    task_id: str,
    service: LayoutService = Depends(get_layout_service),
):
    return service.get_task_status(task_id)


@router.get("/albums/{album_id}/state")
def get_album_state(
    album_id: str,
    service: LayoutService = Depends(get_layout_service),
):
    return service.get_album_state(album_id)


@router.get("/albums/{album_id}/layout")
def get_layout(
    album_id: str,
    version: int | None = None,
    service: LayoutService = Depends(get_layout_service),
):
    return service.get_layout(album_id, version)
