from pydantic import Field

from pixelpress_backend.core.enums import OperationType
from pixelpress_backend.models.common import Actor, BaseSchema, JSONDict


class UserOperationRequest(BaseSchema):
    operation_id: str
    album_id: str
    base_version: int
    expected_status: str = "draft"
    op: OperationType
    payload: JSONDict = Field(default_factory=dict)
    actor: Actor


class UserOperationResponse(BaseSchema):
    operation_id: str
    accepted: bool
    message: str
    next_task_id: str | None = None
