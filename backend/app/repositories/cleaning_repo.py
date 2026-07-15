from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cleaning_duplicate_group import CleaningDuplicateGroup
from app.models.cleaning_duplicate_member import CleaningDuplicateMember
from app.models.photo_cleaning_decision_event import PhotoCleaningDecisionEvent


class CleaningRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_groups(self, album_id: str, task_id: str, analysis_version: str, groups: list[dict]) -> list[CleaningDuplicateGroup]:
        await self.session.execute(delete(CleaningDuplicateGroup).where(CleaningDuplicateGroup.album_id == album_id))
        created: list[CleaningDuplicateGroup] = []
        for payload in groups:
            group = CleaningDuplicateGroup(
                album_id=album_id,
                task_id=task_id,
                analysis_version=analysis_version,
                group_type=payload["group_type"],
                confidence=payload["confidence"],
                preferred_photo_id=payload["preferred_photo_id"],
                thresholds_json=payload.get("thresholds"),
                explanation_json=payload.get("explanation"),
            )
            self.session.add(group)
            await self.session.flush()
            for item in payload["members"]:
                member = CleaningDuplicateMember(
                    group_id=group.id,
                    photo_id=item["photo_id"],
                    relation_type=item["relation_type"],
                    hamming_distance=item.get("hamming_distance"),
                    burst_time_delta_ms=item.get("burst_time_delta_ms"),
                    preferred_score=item["preferred_score"],
                    rank=item["rank"],
                    is_preferred=item["is_preferred"],
                    auto_excluded=item["auto_excluded"],
                    factors_json=item.get("factors"),
                )
                self.session.add(member)
            created.append(group)
        await self.session.flush()
        return created

    async def list_groups(self, album_id: str) -> list[CleaningDuplicateGroup]:
        result = await self.session.execute(
            select(CleaningDuplicateGroup)
            .where(CleaningDuplicateGroup.album_id == album_id)
            .options(selectinload(CleaningDuplicateGroup.members))
            .order_by(CleaningDuplicateGroup.created_at, CleaningDuplicateGroup.id)
        )
        return list(result.scalars().all())

    async def get_group(self, album_id: str, group_id: str) -> CleaningDuplicateGroup | None:
        result = await self.session.execute(
            select(CleaningDuplicateGroup)
            .where(CleaningDuplicateGroup.album_id == album_id, CleaningDuplicateGroup.id == group_id)
            .options(selectinload(CleaningDuplicateGroup.members))
        )
        return result.scalar_one_or_none()

    async def clear_groups(self, album_id: str) -> None:
        await self.session.execute(delete(CleaningDuplicateGroup).where(CleaningDuplicateGroup.album_id == album_id))
        await self.session.flush()

    async def add_decision_event(self, payload: dict) -> PhotoCleaningDecisionEvent:
        event = PhotoCleaningDecisionEvent(**payload)
        self.session.add(event)
        await self.session.flush()
        return event
