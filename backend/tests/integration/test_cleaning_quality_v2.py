from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.engines.cleaning_engine.face_analyzer import FaceFeatureExtractor, MediaPipeFaceAnalyzer, _DetectedFace
from app.engines.cleaning_engine.local_analyzer import LocalPhotoAnalyzer
from app.engines.cleaning_engine.review_queue import build_review_queue
from app.engines.cleaning_engine.service import _preferred_sort_key, build_cleaning_result
from app.engines.cleaning_engine.technical_analyzer import analyze_sharpness


def _checkerboard(size: int = 1024, cell: int = 16) -> Image.Image:
    rows, columns = np.indices((size, size))
    pixels = ((((columns // cell) + (rows // cell)) % 2) * 255).astype(np.uint8)
    return Image.fromarray(pixels).convert("RGB")


def _motion_blurred_texture() -> Image.Image:
    generator = np.random.default_rng(4)
    image = Image.new("L", (1024, 1024), 128)
    draw = ImageDraw.Draw(image)
    for _ in range(1000):
        x = int(generator.integers(0, 1000))
        y = int(generator.integers(0, 1000))
        width = int(generator.integers(3, 40))
        height = int(generator.integers(3, 40))
        draw.rectangle((x, y, x + width, y + height), fill=int(generator.integers(0, 256)))

    source = np.asarray(image, dtype=np.float64)
    kernel_width = 641
    radius = kernel_width // 2
    padded = np.pad(source, ((0, 0), (radius, radius)), mode="edge")
    cumulative = np.pad(np.cumsum(padded, axis=1), ((0, 0), (1, 0)))
    blurred = (cumulative[:, kernel_width:] - cumulative[:, :-kernel_width]) / kernel_width
    return Image.fromarray(blurred.astype(np.uint8)).convert("RGB")


def _analysis(photo_id: str, *, hard_reject: bool, quality_score: float, phash: str) -> dict:
    return {
        "photo_id": photo_id,
        "content_sha256": photo_id,
        "perceptual_hash": phash,
        "analysis_version": "test-v2",
        "quality_score": quality_score,
        "suggestion": "remove" if hard_reject else "keep",
        "confidence": 0.99 if hard_reject else 0.9,
        "issues": ["sharpness_severe"] if hard_reject else [],
        "hard_reject": hard_reject,
        "hard_reject_reason": "unrecoverable_blur" if hard_reject else None,
        "features": {
            "sharpness": {"score": 0.05 if hard_reject else 0.8, "hard_reject": hard_reject},
            "exposure": {"score": 0.8},
            "resolution": {"score": 0.8, "width": 1200, "height": 1200},
            "composition": {"aspect_ratio": 1.0, "orientation": "square"},
            "color_histogram": [0.0] * 48,
        },
        "taken_at": None,
        "device_model": None,
        "uploaded_at": None,
    }


def test_gaussian_defocus_only_hits_hard_floor_when_texture_remains_measurable():
    sharp = analyze_sharpness(_checkerboard())
    blurred = analyze_sharpness(_checkerboard().filter(ImageFilter.GaussianBlur(9)))

    assert sharp["severity"] == "ok"
    assert sharp["hard_reject"] is False
    assert blurred["texture_sufficient"] is True
    assert blurred["severity"] == "severe"
    assert blurred["hard_reject"] is True
    assert blurred["hard_reject_reason"] == "unrecoverable_blur"


def test_low_texture_is_undetermined_and_never_hits_hard_floor():
    result = analyze_sharpness(Image.new("RGB", (1600, 1200), (128, 128, 128)))

    assert result["texture_sufficient"] is False
    assert result["severity"] == "undetermined"
    assert result["hard_reject"] is False


def test_screenshot_exposure_is_not_applicable_and_technical_warnings_do_not_require_review():
    image = Image.new("RGB", (1200, 700), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 1160, 660), outline="black", width=5)
    draw.rectangle((80, 100, 700, 180), fill=(230, 230, 230))
    output = BytesIO()
    image.save(output, format="PNG")

    result = LocalPhotoAnalyzer("b2-local-v3").analyze(output.getvalue(), {
        "id": "screenshot",
        "filename": "屏幕截图 2026-07-17.png",
        "content_type": "image/png",
    })

    assert result["features"]["content_profile"]["capture_kind"] == "screenshot_or_graphic"
    assert result["features"]["exposure"]["severity"] == "not_applicable"
    assert result["features"]["exposure"]["score"] is None
    assert not any(issue.startswith("exposure_") for issue in result["issues"])
    assert result["suggestion"] == "keep"


def test_same_blur_is_consistent_after_source_is_scaled_to_1024():
    large = _checkerboard(2048, 32).filter(ImageFilter.GaussianBlur(18))
    scaled = large.resize((1024, 1024), Image.Resampling.LANCZOS)

    assert analyze_sharpness(large)["hard_reject"] is True
    assert analyze_sharpness(scaled)["hard_reject"] is True


def test_directional_motion_blur_produces_directional_evidence_and_hard_floor():
    result = analyze_sharpness(_motion_blurred_texture())

    assert result["scales"]["1024"]["motion_anisotropy"] >= 0.5
    assert result["scales"]["1024"]["motion_blur_score"] >= 0.3
    assert result["hard_reject"] is True


def test_hard_reject_outranks_duplicate_preference_and_uses_dedicated_source():
    blurred = _analysis("blurred", hard_reject=True, quality_score=10.0, phash="0000000000000000")
    clear = _analysis("clear", hard_reject=False, quality_score=5.0, phash="0000000000000001")
    result = build_cleaning_result(
        "album",
        [blurred, clear],
        auto_exclude_exact=False,
        auto_exclude_quality=True,
    )

    assert result["groups"][0]["preferred_photo_id"] == "clear"
    assert blurred["auto_excluded"] is True
    assert blurred["auto_exclusion_source"] == "system_unrecoverable_blur"


def test_face_risks_affect_burst_preference_before_global_quality():
    risky = _analysis("risky", hard_reject=False, quality_score=10.0, phash="0")
    clear = _analysis("clear", hard_reject=False, quality_score=6.0, phash="1")
    for item in (risky, clear):
        item["features"]["faces"] = {
            "detected_count": 2,
            "aggregate": {"clarity_p20": 0.8},
        }
    risky["features"]["faces"]["aggregate"]["closed_eye_suspected_count"] = 1

    assert _preferred_sort_key(clear) < _preferred_sort_key(risky)


def test_missing_face_models_degrade_without_failing_photo_analysis():
    analyzer = MediaPipeFaceAnalyzer(
        enabled=True,
        detector_model_path="models/cleaning/does-not-exist.tflite",
        landmarker_model_path="models/cleaning/does-not-exist.task",
    )
    output = BytesIO()
    _checkerboard(256, 16).save(output, format="JPEG")

    result = LocalPhotoAnalyzer("test-v2", face_analyzer=analyzer).analyze(output.getvalue(), {"id": "photo"})

    assert result["features"]["faces"]["available"] is False
    assert result["features"]["faces"]["fallback_reason"] == "model_missing"
    assert "analysis_failed" not in result["issues"]
    assert "face_analysis_failed" in result["issues"]
    assert result["suggestion"] == "keep"


def test_review_queue_absorbs_group_member_reasons_without_duplicate_questions():
    def photo(photo_id: str, issues: list[str]) -> SimpleNamespace:
        return SimpleNamespace(
            id=photo_id,
            cleaning_decision=None,
            cleaning_suggestion="review",
            cleaning_issues=issues,
            quality_score=5.0,
            cleaning_confidence=0.75,
        )

    photos = [
        photo("a", ["closed_eyes_suspected"]),
        photo("b", ["sharpness_warning"]),
        photo("c", ["exposure_warning"]),
    ]
    group = SimpleNamespace(
        id="duplicate-1",
        group_type="burst",
        confidence=0.9,
        preferred_photo_id="a",
        members=[
            SimpleNamespace(id="member-a", photo_id="a", rank=1),
            SimpleNamespace(id="member-b", photo_id="b", rank=2),
        ],
    )

    queue = build_review_queue(photos, [group])
    asked_ids = [photo_id for item in queue for photo_id in item["photo_ids"]]

    assert len(queue) == 2
    assert asked_ids.count("a") == 1
    assert asked_ids.count("b") == 1
    assert asked_ids.count("c") == 1
    group_item = next(item for item in queue if item["kind"] == "duplicate_group")
    assert set(group_item["reason_codes"]) >= {"duplicate_burst", "closed_eyes_suspected", "sharpness_warning"}


def test_bundled_mediapipe_models_load_without_runtime_download():
    analyzer = FaceFeatureExtractor(
        enabled=True,
        detector_model_path="models/cleaning/blaze_face_full_range_sparse.tflite",
        landmarker_model_path="models/cleaning/face_landmarker.task",
    )

    result = analyzer.analyze(Image.new("RGB", (640, 480), "white"))

    assert result["available"] is True
    assert result["detected_count"] == 0
    assert result["version"] == "hybrid-face-v2"


def test_anime_raw_outputs_use_combined_confidence_and_nms_without_real_face_traits():
    class FakeAnimeNet:
        def setInput(self, blob):  # noqa: N802, ANN001
            assert blob.shape == (1, 3, 608, 608)

        def getUnconnectedOutLayersNames(self):  # noqa: N802
            return ("boxes", "classes", "objectness")

        def forward(self, names):  # noqa: ANN001
            assert tuple(names) == ("boxes", "classes", "objectness")
            return [
                np.asarray([[[120, 80, 300, 260], [125, 85, 305, 265]]], dtype=np.float32),
                np.asarray([[[0.95], [0.92]]], dtype=np.float32),
                np.asarray([[0.95, 0.90]], dtype=np.float32),
            ]

    analyzer = FaceFeatureExtractor(
        enabled=True,
        detector_model_path="unused",
        landmarker_model_path="unused",
        anime_model_path="unused",
    )
    analyzer._anime_net = FakeAnimeNet()
    analyzer._load = lambda: (_ for _ in ()).throw(AssertionError("real detector must not load"))  # type: ignore[method-assign]

    result = analyzer.analyze(
        _checkerboard(608, 12),
        content_profile={"capture_kind": "screenshot_or_graphic", "visual_domain": "illustration"},
    )

    assert result["detected_count"] == 1
    assert result["anime_face_count"] == 1
    assert result["real_face_count"] == 0
    assert result["items"][0]["detection_score"] == 0.9025
    assert result["items"][0]["closed_eye_suspected"] is False
    assert result["items"][0]["occlusion_suspected"] is False
    assert result["items"][0]["capabilities"] == ["count", "bbox", "edge_crop", "clarity"]


def test_face_analysis_marks_edge_crop_closed_eyes_and_keeps_only_compact_features():
    analyzer = MediaPipeFaceAnalyzer(
        enabled=False,
        detector_model_path="unused",
        landmarker_model_path="unused",
    )
    analyzer._mp_image = lambda image: None  # type: ignore[method-assign]
    landmarks = [
        SimpleNamespace(x=0.0, y=0.2),
        SimpleNamespace(x=0.2, y=0.2),
        SimpleNamespace(x=0.0, y=0.4),
        SimpleNamespace(x=0.2, y=0.4),
    ]
    categories = [
        SimpleNamespace(category_name="eyeBlinkLeft", score=0.9),
        SimpleNamespace(category_name="eyeBlinkRight", score=0.9),
    ]
    analyzer._landmarker = SimpleNamespace(detect=lambda image: SimpleNamespace(
        face_landmarks=[landmarks],
        face_blendshapes=[categories],
    ))
    detected = [_DetectedFace(
        bbox=(0.0, 0.2, 0.2, 0.2),
        score=0.95,
        keypoints=[(0.05, 0.27), (0.15, 0.27)],
    )]

    result = analyzer._analyze_faces(_checkerboard(800, 20), _checkerboard(800, 20), detected)[0]

    assert result["edge_crop_suspected"] is True
    assert result["closed_eye_suspected"] is True
    assert result["occlusion_suspected"] is False
    assert result["clarity"] is not None
    assert "landmarks" not in result


def test_large_image_uses_bounded_tiled_face_fallback():
    analyzer = MediaPipeFaceAnalyzer(
        enabled=False,
        detector_model_path="unused",
        landmarker_model_path="unused",
    )
    calls = 0

    def fake_detect(image: Image.Image) -> list[_DetectedFace]:
        nonlocal calls
        calls += 1
        if calls == 2:
            return [_DetectedFace(
                bbox=(0.1, 0.1, 0.2, 0.2),
                score=0.9,
                keypoints=[(0.15, 0.15), (0.25, 0.15)],
            )]
        return []

    analyzer._detect_faces = fake_detect  # type: ignore[method-assign]
    source = Image.new("RGB", (3000, 2500), "white")
    detected = analyzer._detect_faces_with_tiled_fallback(source, analyzer._analysis_image(source))

    assert calls == 5
    assert len(detected) == 1
    assert tuple(round(value, 2) for value in detected[0].bbox) == (0.06, 0.06, 0.12, 0.12)
