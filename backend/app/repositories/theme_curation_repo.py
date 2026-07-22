from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.album_theme_profile import AlbumThemeProfile
from app.models.photo_theme_assessment import PhotoThemeAssessment
from app.models.photo_theme_decision_event import PhotoThemeDecisionEvent


class ThemeCurationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_profile(self, payload: dict) -> AlbumThemeProfile:
        profile = AlbumThemeProfile(**payload)
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def latest_profile(self, album_id: str) -> AlbumThemeProfile | None:
        result = await self.session.execute(
            select(AlbumThemeProfile)
            .where(AlbumThemeProfile.album_id == album_id, AlbumThemeProfile.status != "superseded")
            .order_by(AlbumThemeProfile.created_at.desc(), AlbumThemeProfile.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_profile(self, album_id: str, profile_id: str) -> AlbumThemeProfile | None:
        result = await self.session.execute(
            select(AlbumThemeProfile).where(
                AlbumThemeProfile.album_id == album_id,
                AlbumThemeProfile.id == profile_id,
            )
        )
        return result.scalar_one_or_none()

    async def confirmed_profile(self, album_id: str, content_revision: int) -> AlbumThemeProfile | None:
        result = await self.session.execute(
            select(AlbumThemeProfile)
            .where(
                AlbumThemeProfile.album_id == album_id,
                AlbumThemeProfile.status == "confirmed",
                AlbumThemeProfile.confirmed_revision == content_revision,
            )
            .order_by(AlbumThemeProfile.confirmed_at.desc(), AlbumThemeProfile.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def supersede_active_profiles(self, album_id: str, *, except_profile_id: str | None = None) -> None:
        result = await self.session.execute(
            select(AlbumThemeProfile).where(
                AlbumThemeProfile.album_id == album_id,
                AlbumThemeProfile.status != "superseded",
            )
        )
        for profile in result.scalars().all():
            if profile.id == except_profile_id:
                continue
            profile.status = "superseded"
        await self.session.flush()

    async def update_profile(self, profile: AlbumThemeProfile, updates: dict) -> AlbumThemeProfile:
        for key, value in updates.items():
            setattr(profile, key, value)
        await self.session.flush()
        return profile

    async def replace_assessments(self, profile: AlbumThemeProfile, payloads: list[dict]) -> list[PhotoThemeAssessment]:
        await self.session.execute(delete(PhotoThemeAssessment).where(PhotoThemeAssessment.profile_id == profile.id))
        created: list[PhotoThemeAssessment] = []
        for payload in payloads:
            assessment = PhotoThemeAssessment(profile_id=profile.id, album_id=profile.album_id, **payload)
            self.session.add(assessment)
            created.append(assessment)
        await self.session.flush()
        return created

    async def list_assessments(self, profile_id: str) -> list[PhotoThemeAssessment]:
        result = await self.session.execute(
            select(PhotoThemeAssessment)
            .where(PhotoThemeAssessment.profile_id == profile_id)
            .options(selectinload(PhotoThemeAssessment.photo))
            .order_by(PhotoThemeAssessment.relevance_score.desc(), PhotoThemeAssessment.photo_id)
        )
        return list(result.scalars().all())

    async def assessment_map(self, profile_id: str) -> dict[str, PhotoThemeAssessment]:
        return {item.photo_id: item for item in await self.list_assessments(profile_id)}

    async def count_unresolved_reviews(self, profile_id: str) -> int:
        assessments = await self.list_assessments(profile_id)
        return sum((item.user_decision or item.suggested_decision) == "review" for item in assessments)

    async def update_decisions(
        self,
        profile: AlbumThemeProfile,
        photo_ids: list[str],
        decision: str | None,
    ) -> int:
        assessments = await self.assessment_map(profile.id)
        changed = 0
        for photo_id in photo_ids:
            assessment = assessments.get(photo_id)
            if assessment is None or assessment.user_decision == decision:
                continue
            self.session.add(PhotoThemeDecisionEvent(
                profile_id=profile.id,
                album_id=profile.album_id,
                photo_id=photo_id,
                previous_decision=assessment.user_decision,
                decision=decision,
                source="user",
                context_json={"operation": "theme_review"},
            ))
            assessment.user_decision = decision
            changed += 1
        await self.session.flush()
        return changed
