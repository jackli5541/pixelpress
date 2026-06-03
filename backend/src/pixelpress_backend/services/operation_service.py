from __future__ import annotations

from uuid import uuid4

from pixelpress_backend.core.enums import AlbumStatus, BookLayoutStatus, OperationType, TaskStatus, TaskType
from pixelpress_backend.models.domain import TaskState, UserOperation
from pixelpress_backend.models.operations import UserOperationRequest, UserOperationResponse
from pixelpress_backend.repositories.memory import store
from pixelpress_backend.services.exceptions import ConflictError, InvalidStateError
from pixelpress_backend.services.layout_service import layout_service


class OperationService:
    def apply_operation(self, request: UserOperationRequest) -> UserOperationResponse:
        album = layout_service.get_album_state(request.album_id)
        layout = layout_service.get_layout(request.album_id, request.base_version)

        if layout.version != request.base_version:
            raise ConflictError("操作 base_version 与当前版本不一致。")
        if layout.status != BookLayoutStatus.DRAFT:
            raise InvalidStateError("仅允许对 draft 布局应用编辑操作。")

        operation = UserOperation(
            operation_id=request.operation_id,
            album_id=request.album_id,
            base_version=request.base_version,
            op_type=request.op,
            payload=request.payload,
            actor=request.actor,
        )
        store.operations[operation.operation_id] = operation

        next_task_id = None
        if request.op in {
            OperationType.REPLACE_PHOTO,
            OperationType.SWAP_PAGE_PHOTOS,
            OperationType.ADJUST_CROP,
            OperationType.MARK_PAGE_DISLIKED,
            OperationType.SET_HERO_PERSON,
            OperationType.MERGE_CHAPTERS,
            OperationType.SPLIT_CHAPTER,
            OperationType.REORDER_CHAPTERS,
        }:
            next_task_id = str(uuid4())
            task = TaskState(
                task_id=next_task_id,
                album_id=request.album_id,
                task_type=TaskType.PARTIAL_REGENERATE,
                status=TaskStatus.QUEUED,
                idempotency_key=request.operation_id,
                base_version=request.base_version,
            )
            store.tasks[next_task_id] = task

        if request.op == OperationType.LOCK_LAYOUT:
            layout.status = BookLayoutStatus.LOCKED
            album.status = AlbumStatus.LOCKED
            album.allow_export = not layout.is_partial
            album.allow_order = False

        return UserOperationResponse(
            operation_id=request.operation_id,
            accepted=True,
            message="操作已接收，具体逻辑待对应能力模块实现。",
            next_task_id=next_task_id,
        )


operation_service = OperationService()
