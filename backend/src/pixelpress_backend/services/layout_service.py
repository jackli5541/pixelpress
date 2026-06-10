from __future__ import annotations

from uuid import uuid4

from pixelpress_backend.core.enums import AlbumStatus, FeatureStatus, TaskStatus, TaskType
from pixelpress_backend.graph.workflow import layout_workflow
from pixelpress_backend.models.domain import (
    AlbumState,
    BookLayout,
    GenerateLayoutRequest,
    LayoutGenerateResponse,
    TaskState,
    TaskStatusResponse,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState
from pixelpress_backend.repositories.memory import store
from pixelpress_backend.services.exceptions import ConflictError, InvalidStateError, NotFoundError


class LayoutService:
    def ensure_album(self, album_id: str) -> AlbumState:
        album = store.albums.get(album_id)
        if album is None:
            album = AlbumState(album_id=album_id, feature_status=FeatureStatus.READY)
            store.albums[album_id] = album
        return album

    def generate_layout(self, request: GenerateLayoutRequest) -> LayoutGenerateResponse:
        album = self.ensure_album(request.album_id)
        idempotency_scope = f"{request.album_id}:{request.idempotency_key}"
        existing_task_id = store.idempotency_map.get(idempotency_scope)
        if existing_task_id:
            task = store.tasks[existing_task_id]
            return LayoutGenerateResponse(
                task_id=task.task_id,
                task_status=task.status,
                album_status=album.status,
                book_layout_version=task.result_version,
            )

        if album.status == AlbumStatus.LOCKED:
            raise InvalidStateError("相册已锁定，不能直接生成新布局，请创建新版本流程。")

        if request.base_version is not None and album.current_layout_version != request.base_version:
            raise ConflictError("base_version 与当前布局版本不一致。")

        running_full_tasks = [
            item for item in store.tasks.values()
            if item.album_id == request.album_id
            and item.task_type == TaskType.LAYOUT_GENERATE
            and item.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}
        ]
        if running_full_tasks:
            raise ConflictError("同一相册当前已有全书级生成任务在执行。")

        if album.feature_status not in {FeatureStatus.READY, FeatureStatus.PARTIAL} and request.force_mode != "slow_path":
            raise InvalidStateError("特征尚未就绪，未启用 slow_path。")

        task_id = str(uuid4())
        task = TaskState(
            task_id=task_id,
            album_id=request.album_id,
            task_type=TaskType.LAYOUT_GENERATE,
            status=TaskStatus.QUEUED,
            idempotency_key=request.idempotency_key,
            base_version=request.base_version,
        )
        store.tasks[task_id] = task
        store.idempotency_map[idempotency_scope] = task_id

        album.status = AlbumStatus.GENERATING
        task.status = TaskStatus.RUNNING

        workflow_state = LayoutWorkflowState(request=request, album=album, task=task)
        result_state = layout_workflow.invoke(workflow_state.model_dump(mode="python"))

        final_layout_data = result_state.get("final_layout")
        final_layout = BookLayout.model_validate(final_layout_data) if final_layout_data else None
        if final_layout is None:
            task.status = TaskStatus.FAILED
            raise InvalidStateError("工作流未产出最终布局。")

        store.layouts.setdefault(request.album_id, {})[final_layout.version] = final_layout
        album.current_layout_version = final_layout.version
        album.latest_completed_task_id = task.task_id
        album.status = AlbumStatus.REVIEWABLE
        album.allow_preview = True
        album.allow_export = False
        album.allow_order = False

        if final_layout.is_partial:
            task.status = TaskStatus.PARTIAL
            album.allow_export = False
            album.allow_order = False
        else:
            task.status = TaskStatus.COMPLETED
        task.result_version = final_layout.version

        return LayoutGenerateResponse(
            task_id=task.task_id,
            task_status=task.status,
            album_status=album.status,
            book_layout_version=final_layout.version,
        )

    def get_task_status(self, task_id: str) -> TaskStatusResponse:
        task = store.tasks.get(task_id)
        if task is None:
            raise NotFoundError("任务不存在。")

        album = self.ensure_album(task.album_id)
        result = None
        if task.result_version is not None:
            layout = store.layouts[task.album_id][task.result_version]
            result = {
                "book_layout": layout.model_dump(mode="json"),
                "allow_preview": album.allow_preview,
                "allow_export": album.allow_export,
                "allow_order": album.allow_order,
            }

        error = None
        if task.error_code:
            error = {"error_code": task.error_code}

        return TaskStatusResponse(
            task_id=task.task_id,
            task_status=task.status,
            album_status=album.status,
            result=result,
            error=error,
        )

    def get_album_state(self, album_id: str) -> AlbumState:
        return self.ensure_album(album_id)

    def get_layout(self, album_id: str, version: int | None = None):
        album = self.ensure_album(album_id)
        if album.current_layout_version is None:
            raise NotFoundError("当前相册暂无布局版本。")
        resolved_version = version or album.current_layout_version
        layout = store.layouts.get(album_id, {}).get(resolved_version)
        if layout is None:
            raise NotFoundError("指定布局版本不存在。")
        return layout


layout_service = LayoutService()
