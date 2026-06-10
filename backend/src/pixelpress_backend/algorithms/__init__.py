from __future__ import annotations

from pixelpress_backend.algorithms.feature_extraction import (
    CLIPEmbeddingGenerator,
    DuplicateDetector,
    FaceNetClusterer,
    ImageQualityAnalyzer,
    PerceptualHash,
    SceneTagGenerator,
    U2NetSaliencyGenerator,
    YOLOFaceDetector,
    YOLOSubjectDetector,
)

__all__ = [
    "CLIPEmbeddingGenerator",
    "DuplicateDetector",
    "FaceNetClusterer",
    "ImageQualityAnalyzer",
    "PerceptualHash",
    "SceneTagGenerator",
    "U2NetSaliencyGenerator",
    "YOLOFaceDetector",
    "YOLOSubjectDetector",
]