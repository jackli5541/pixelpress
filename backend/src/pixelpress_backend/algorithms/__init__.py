from __future__ import annotations

from pixelpress_backend.algorithms.chapter_clustering import ChapterClusteringAlgorithm
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
from pixelpress_backend.algorithms.pagination_planning import PaginationPlanningAlgorithm

__all__ = [
    "ChapterClusteringAlgorithm",
    "CLIPEmbeddingGenerator",
    "DuplicateDetector",
    "FaceNetClusterer",
    "ImageQualityAnalyzer",
    "PaginationPlanningAlgorithm",
    "PerceptualHash",
    "SceneTagGenerator",
    "U2NetSaliencyGenerator",
    "YOLOFaceDetector",
    "YOLOSubjectDetector",
]