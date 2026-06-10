from fastapi import APIRouter, Depends

from pixelpress_backend.api.dependencies import get_operation_service
from pixelpress_backend.models.operations import UserOperationRequest, UserOperationResponse
from pixelpress_backend.services.operation_service import OperationService


router = APIRouter(prefix="/operations", tags=["operations"])


@router.post("", response_model=UserOperationResponse)
def submit_operation(
    request: UserOperationRequest,
    service: OperationService = Depends(get_operation_service),
):
    return service.apply_operation(request)
