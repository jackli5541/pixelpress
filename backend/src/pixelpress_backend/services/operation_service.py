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
        existing_operation = store.operations.get(request.operation_id)
        if existing_operation is not None:
            self._assert_same_operation(existing_operation, request)
            stored_receipt = store.operation_receipts.get(request.operation_id)
            if stored_receipt is None:
                raise ConflictError("操作幂等记录不完整，请重新生成新的 operation_id。")
            return UserOperationResponse(**stored_receipt)

        album = layout_service.get_album_state(request.album_id)
        if album.current_layout_version != request.base_version:
            raise ConflictError("操作 base_version 与当前版本不一致。")

        layout = layout_service.get_layout(request.album_id, request.base_version)
        if layout.status != request.expected_status:
            raise InvalidStateError("布局状态与 expected_status 不一致。")

        next_task_id = None
        self._validate_operation_preconditions(request, album, layout)
        operation = UserOperation(
            operation_id=request.operation_id,
            album_id=request.album_id,
            base_version=request.base_version,
            op_type=request.op,
            payload=request.payload,
            actor=request.actor,
        )
        store.operations[operation.operation_id] = operation

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
            next_task_id = self._enqueue_task(
                album_id=request.album_id,
                task_type=TaskType.PARTIAL_REGENERATE,
                operation_id=request.operation_id,
                base_version=request.base_version,
            )

        if request.op == OperationType.LOCK_LAYOUT:
            layout.status = BookLayoutStatus.LOCKED
            album.status = AlbumStatus.LOCKED
            album.allow_export = True
            album.allow_order = False
        elif request.op == OperationType.REQUEST_EXPORT:
            next_task_id = self._enqueue_task(
                album_id=request.album_id,
                task_type=TaskType.EXPORT_PDF,
                operation_id=request.operation_id,
                base_version=request.base_version,
            )

        response = UserOperationResponse(
            operation_id=request.operation_id,
            accepted=True,
            message="操作已接收，具体逻辑待对应能力模块实现。",
            next_task_id=next_task_id,
        )
        store.operation_receipts[request.operation_id] = response.model_dump(mode="python")
        return response

    def _assert_same_operation(self, operation: UserOperation, request: UserOperationRequest) -> None:
        if (
            operation.album_id != request.album_id
            or operation.base_version != request.base_version
            or operation.op_type != request.op
            or operation.payload != request.payload
            or operation.actor != request.actor
        ):
            raise ConflictError("operation_id 已存在，且请求内容与历史记录不一致。")

    def _validate_operation_preconditions(self, request, album, layout) -> None:
        if request.op in {
            OperationType.REPLACE_PHOTO,
            OperationType.SWAP_PAGE_PHOTOS,
            OperationType.ADJUST_CROP,
            OperationType.SET_CAPTION,
            OperationType.SET_CHAPTER_TITLE,
            OperationType.MARK_PAGE_DISLIKED,
            OperationType.SET_HERO_PERSON,
            OperationType.MERGE_CHAPTERS,
            OperationType.SPLIT_CHAPTER,
            OperationType.REORDER_CHAPTERS,
            OperationType.LOCK_LAYOUT,
        } and layout.status != BookLayoutStatus.DRAFT:
            raise InvalidStateError("仅允许对 draft 布局应用编辑操作。")

        if request.op == OperationType.LOCK_LAYOUT:
            if album.status != AlbumStatus.REVIEWABLE:
                raise InvalidStateError("仅允许在 reviewable 阶段锁定布局。")
            if layout.is_partial:
                raise InvalidStateError("partial 布局不能被锁定。")
            if self._has_active_tasks(request.album_id):
                raise ConflictError("存在未完成任务，暂不能锁定布局。")

        if request.op == OperationType.REQUEST_EXPORT:
            if layout.status != BookLayoutStatus.LOCKED:
                raise InvalidStateError("仅允许导出 locked 布局。")
            if album.status != AlbumStatus.LOCKED:
                raise InvalidStateError("相册未锁定，不能请求导出。")
            if layout.is_partial or not album.allow_export:
                raise InvalidStateError("当前布局不允许导出。")

        if request.op == OperationType.SUBMIT_ORDER:
            if layout.status != BookLayoutStatus.EXPORTED:
                raise InvalidStateError("仅允许对 exported 布局提交订单。")
            if not album.allow_order:
                raise InvalidStateError("当前相册不允许下单。")

    def _enqueue_task(self, *, album_id: str, task_type: TaskType, operation_id: str, base_version: int) -> str:
        next_task_id = str(uuid4())
        task = TaskState(
            task_id=next_task_id,
            album_id=album_id,
            task_type=task_type,
            status=TaskStatus.QUEUED,
            idempotency_key=operation_id,
            base_version=base_version,
        )
        store.tasks[next_task_id] = task
        return next_task_id

    def _has_active_tasks(self, album_id: str) -> bool:
        return any(
            task.album_id == album_id and task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.PARTIAL}
            for task in store.tasks.values()
        )


operation_service = OperationService()
