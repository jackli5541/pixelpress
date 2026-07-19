from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.engines.theme_pipeline import complete_record_candidate
from app.engines.theme_relevance_engine import QUERY_VERSION, SCORING_VERSION, load_calibration
from app.repositories.album_repo import AlbumRepository
from app.repositories.theme_curation_repo import ThemeCurationRepository
from app.services.chapter_feature_service import ChapterFeatureService
from app.services.serializers import serialize_theme_assessment, serialize_theme_profile


class ThemeWorkspaceBuilder:
    def __init__(self, session: AsyncSession, strategies: set[str]) -> None:
        self.album_repo = AlbumRepository(session)
        self.repo = ThemeCurationRepository(session)
        self.feature_service = ChapterFeatureService(session)
        self.strategies = sorted(strategies)

    async def build(self, album_id: str):  # noqa: ANN201
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        settings = get_settings()
        calibration = load_calibration(settings.theme_relevance_calibration_path)
        try:
            connection = await self.feature_service.resolve_embedding_connection()
            provider, model = connection.provider, connection.model
        except Exception:  # noqa: BLE001
            provider, model = settings.chapter_embedding_provider, settings.chapter_embedding_model
        calibration_status = calibration.compatibility_status(
            provider=provider,
            model=model,
            dimension=settings.chapter_embedding_dimension,
        )
        calibration_payload = {
            "status": calibration_status,
            "auto_decision_enabled": calibration_status == "ready",
            "version": calibration.version,
            "provider": provider,
            "model": model,
            "dimension": settings.chapter_embedding_dimension,
            "query_version": QUERY_VERSION,
            "scoring_version": SCORING_VERSION,
        }
        if not settings.theme_curation_enabled:
            return {
                "enabled": False,
                "phase": "ready_to_cluster",
                "strategies": self.strategies,
                "profile": {
                    "id": "disabled-complete-record",
                    "status": "confirmed",
                    **complete_record_candidate(),
                    "chapter_strategy": "balanced",
                    "fallback_used": True,
                },
                "assessments": [],
                "calibration": {**calibration_payload, "status": "disabled", "auto_decision_enabled": False},
                "summary": {"total": 0, "kept": 0, "suggested_exclude": 0, "uncertain": 0, "review": 0, "excluded": 0},
            }
        profile = await self.repo.latest_profile(album_id)
        if profile is None or profile.analysis_revision != album.theme_input_revision and profile.status != "confirmed":
            phase = "needs_analysis"
        elif profile.status == "candidates_ready":
            phase = "choose_theme"
        elif profile.status == "review_pending":
            phase = "review_theme_photos"
        elif profile.status == "confirmed" and profile.confirmed_revision == album.theme_input_revision:
            phase = "ready_to_cluster"
        else:
            phase = "needs_analysis"
        assessments = (
            await self.repo.list_assessments(profile.id)
            if profile and profile.status in {"review_pending", "confirmed"}
            else []
        )
        return {
            "enabled": True,
            "phase": phase,
            "strategies": self.strategies,
            "profile": serialize_theme_profile(profile) if profile else None,
            "assessments": [serialize_theme_assessment(item) for item in assessments],
            "calibration": calibration_payload,
            "summary": {
                "total": len(assessments),
                "kept": sum((item.user_decision or item.suggested_decision) == "keep" for item in assessments),
                "suggested_exclude": sum(item.suggested_decision == "exclude" for item in assessments),
                "uncertain": sum(item.relevance_label == "uncertain" for item in assessments),
                "review": sum((item.user_decision or item.suggested_decision) == "review" for item in assessments),
                "excluded": sum((item.user_decision or item.suggested_decision) == "exclude" for item in assessments),
            },
        }
