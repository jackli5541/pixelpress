from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import atan2, degrees
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
from PIL import Image

from app.engines.cleaning_engine.technical_analyzer import analyze_sharpness


FACE_ANALYSIS_MAX_EDGE = 1600
FACE_LANDMARK_MIN_SIDE = 64
EYE_ANALYSIS_MIN_SIDE = 96
MAX_LANDMARK_FACES = 20


@dataclass(slots=True)
class _DetectedFace:
    bbox: tuple[float, float, float, float]
    score: float
    keypoints: list[tuple[float, float]]
    detector: str = "mediapipe_real"


def _iou(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    x1 = max(lx, rx)
    y1 = max(ly, ry)
    x2 = min(lx + lw, rx + rw)
    y2 = min(ly + lh, ry + rh)
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = lw * lh + rw * rh - intersection
    return intersection / union if union > 0 else 0.0


def _nms(faces: list[_DetectedFace], threshold: float = 0.35) -> list[_DetectedFace]:
    selected: list[_DetectedFace] = []
    for face in sorted(faces, key=lambda item: item.score, reverse=True):
        if all(_iou(face.bbox, existing.bbox) < threshold for existing in selected):
            selected.append(face)
    return selected


def _expanded_crop(
    image: Image.Image,
    bbox: tuple[float, float, float, float],
    keypoints: list[tuple[float, float]],
    padding: float = 0.15,
) -> Image.Image:
    x, y, width, height = bbox
    pad_x = width * padding
    pad_y = height * padding
    left = max(0, round((x - pad_x) * image.width))
    top = max(0, round((y - pad_y) * image.height))
    right = min(image.width, round((x + width + pad_x) * image.width))
    bottom = min(image.height, round((y + height + pad_y) * image.height))
    crop = image.crop((left, top, right, bottom))
    if len(keypoints) >= 2:
        first_eye, second_eye = keypoints[:2]
        if first_eye[0] > second_eye[0]:
            first_eye, second_eye = second_eye, first_eye
        angle = degrees(atan2(second_eye[1] - first_eye[1], second_eye[0] - first_eye[0]))
        if abs(angle) <= 45:
            crop = crop.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=False)
    return crop.resize((192, 192), Image.Resampling.LANCZOS)


def _blendshape_map(categories: list[Any]) -> dict[str, float]:
    return {
        str(getattr(item, "category_name", "")): float(getattr(item, "score", 0.0))
        for item in categories
        if getattr(item, "category_name", None)
    }


class MediaPipeFaceAnalyzer:
    version = "hybrid-face-v2"

    def __init__(
        self,
        *,
        enabled: bool,
        detector_model_path: str,
        landmarker_model_path: str,
        anime_model_path: str | None = None,
        anime_enabled: bool = True,
        pose_enabled: bool = False,
        pose_model_path: str | None = None,
    ) -> None:
        self.enabled = enabled
        self.detector_model_path = Path(detector_model_path)
        self.landmarker_model_path = Path(landmarker_model_path)
        self.anime_model_path = Path(anime_model_path) if anime_model_path else None
        self.anime_enabled = anime_enabled
        self.pose_enabled = pose_enabled
        self.pose_model_path = Path(pose_model_path) if pose_model_path else None
        self._lock = Lock()
        self._loaded = False
        self._load_error: str | None = None
        self._mp: Any = None
        self._detector: Any = None
        self._landmarker: Any = None
        self._pose_landmarker: Any = None
        self._anime_net: Any = None
        self._anime_load_error: str | None = None
        self._anime_inference_error: str | None = None

    @staticmethod
    def _verify_models(paths: list[Path]) -> None:
        manifest_path = paths[0].parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {item["name"]: item["sha256"] for item in manifest.get("models", [])}
        for path in paths:
            if not path.is_file() or path.name not in expected:
                raise FileNotFoundError(path)
            if sha256(path.read_bytes()).hexdigest() != expected[path.name]:
                raise ValueError(f"model checksum mismatch: {path.name}")

    def _load(self) -> None:
        if self._loaded or self._load_error or not self.enabled:
            return
        if not self.detector_model_path.is_file() or not self.landmarker_model_path.is_file():
            self._load_error = "model_missing"
            return
        try:
            import mediapipe as mp

            required_paths = [self.detector_model_path, self.landmarker_model_path]
            if self.pose_enabled and self.pose_model_path:
                required_paths.append(self.pose_model_path)
            self._verify_models(required_paths)

            base_options = mp.tasks.BaseOptions
            running_mode = mp.tasks.vision.RunningMode
            detector_options = mp.tasks.vision.FaceDetectorOptions(
                base_options=base_options(model_asset_path=str(self.detector_model_path)),
                running_mode=running_mode.IMAGE,
                min_detection_confidence=0.5,
                min_suppression_threshold=0.3,
            )
            landmarker_options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=base_options(model_asset_path=str(self.landmarker_model_path)),
                running_mode=running_mode.IMAGE,
                num_faces=MAX_LANDMARK_FACES,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=True,
            )
            self._detector = mp.tasks.vision.FaceDetector.create_from_options(detector_options)
            self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(landmarker_options)
            if self.pose_enabled and self.pose_model_path and self.pose_model_path.is_file():
                pose_options = mp.tasks.vision.PoseLandmarkerOptions(
                    base_options=base_options(model_asset_path=str(self.pose_model_path)),
                    running_mode=running_mode.IMAGE,
                    num_poses=10,
                    min_pose_detection_confidence=0.5,
                    min_pose_presence_confidence=0.5,
                    output_segmentation_masks=True,
                )
                self._pose_landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(pose_options)
            self._mp = mp
            self._loaded = True
        except Exception as exc:  # noqa: BLE001
            self._load_error = exc.__class__.__name__

    def _load_anime(self) -> None:
        if self._anime_net is not None or self._anime_load_error or not self.anime_enabled:
            return
        if self.anime_model_path is None or not self.anime_model_path.is_file():
            self._anime_load_error = "model_missing"
            return
        try:
            import cv2

            self._verify_models([self.anime_model_path])
            self._anime_net = cv2.dnn.readNetFromONNX(str(self.anime_model_path))
        except Exception as exc:  # noqa: BLE001
            self._anime_load_error = exc.__class__.__name__

    @staticmethod
    def _analysis_image(image: Image.Image) -> Image.Image:
        result = image.copy()
        result.thumbnail((FACE_ANALYSIS_MAX_EDGE, FACE_ANALYSIS_MAX_EDGE), Image.Resampling.LANCZOS)
        return result

    def _mp_image(self, image: Image.Image):  # noqa: ANN201
        rgb = np.ascontiguousarray(np.asarray(image.convert("RGB"), dtype=np.uint8))
        return self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)

    def _detect_faces(self, image: Image.Image) -> list[_DetectedFace]:
        result = self._detector.detect(self._mp_image(image))
        faces: list[_DetectedFace] = []
        for detection in result.detections:
            box = detection.bounding_box
            bbox = (
                max(0.0, box.origin_x / image.width),
                max(0.0, box.origin_y / image.height),
                min(1.0, box.width / image.width),
                min(1.0, box.height / image.height),
            )
            score = float(detection.categories[0].score) if detection.categories else 0.0
            keypoints = [(float(point.x), float(point.y)) for point in detection.keypoints]
            faces.append(_DetectedFace(bbox=bbox, score=score, keypoints=keypoints, detector="mediapipe_real"))
        return _nms(faces)

    def _detect_anime_faces(self, image: Image.Image) -> list[_DetectedFace]:
        if self._anime_net is None:
            return []
        import cv2

        source = np.asarray(image.convert("RGB"), dtype=np.uint8)[:, :, ::-1]
        source_height, source_width = source.shape[:2]
        input_size = 608
        scale = min(input_size / max(1, source_width), input_size / max(1, source_height))
        resized_width = max(1, round(source_width * scale))
        resized_height = max(1, round(source_height * scale))
        resized = cv2.resize(source, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
        pad_x = (input_size - resized_width) // 2
        pad_y = (input_size - resized_height) // 2
        canvas = np.zeros((input_size, input_size, 3), dtype=np.uint8)
        canvas[pad_y:pad_y + resized_height, pad_x:pad_x + resized_width] = resized
        blob = cv2.dnn.blobFromImage(canvas, scalefactor=1 / 255.0, size=(input_size, input_size), swapRB=True, crop=False)
        self._anime_net.setInput(blob)
        output_names = self._anime_net.getUnconnectedOutLayersNames()
        raw_outputs = self._anime_net.forward(output_names)
        outputs = raw_outputs if isinstance(raw_outputs, (list, tuple)) else [raw_outputs]
        box_output = next(
            (np.asarray(output) for output in outputs if isinstance(output, np.ndarray) and output.ndim == 3 and output.shape[-1] == 4),
            None,
        )
        class_output = next(
            (np.asarray(output) for output in outputs if isinstance(output, np.ndarray) and output.ndim == 3 and output.shape[-1] == 1),
            None,
        )
        objectness_output = next(
            (np.asarray(output) for output in outputs if isinstance(output, np.ndarray) and output.ndim == 2),
            None,
        )
        if box_output is None or class_output is None or objectness_output is None:
            return []
        boxes = box_output.reshape(-1, 4)
        scores = class_output.reshape(-1) * objectness_output.reshape(-1)
        if len(boxes) != len(scores):
            return []
        faces: list[_DetectedFace] = []
        for row, raw_score in zip(boxes, scores, strict=True):
            score = float(raw_score)
            if score < 0.70:
                continue
            x1, y1, x2, y2 = (float(value) for value in row[:4])
            if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 2.5:
                x1, x2 = x1 * input_size, x2 * input_size
                y1, y2 = y1 * input_size, y2 * input_size
            x1 = (x1 - pad_x) / max(1, resized_width)
            x2 = (x2 - pad_x) / max(1, resized_width)
            y1 = (y1 - pad_y) / max(1, resized_height)
            y2 = (y2 - pad_y) / max(1, resized_height)
            x1, y1 = max(0.0, x1), max(0.0, y1)
            x2, y2 = min(1.0, x2), min(1.0, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            faces.append(_DetectedFace(
                bbox=(x1, y1, x2 - x1, y2 - y1),
                score=score,
                keypoints=[],
                detector="anime_yolov3",
            ))
        return _nms(faces, threshold=0.40)

    def _detect_faces_with_tiled_fallback(self, source: Image.Image, analysis_image: Image.Image) -> list[_DetectedFace]:
        detected = self._detect_faces(analysis_image)
        largest_face_side = max(
            (min(face.bbox[2] * source.width, face.bbox[3] * source.height) for face in detected),
            default=0.0,
        )
        if max(source.size) <= 2400 or (detected and largest_face_side >= EYE_ANALYSIS_MIN_SIDE):
            return detected

        tile_width = min(source.width, round(source.width * 0.6))
        tile_height = min(source.height, round(source.height * 0.6))
        left_positions = sorted({0, source.width - tile_width})
        top_positions = sorted({0, source.height - tile_height})
        tiled_faces: list[_DetectedFace] = []
        for top in top_positions:
            for left in left_positions:
                tile = source.crop((left, top, left + tile_width, top + tile_height))
                tile.thumbnail((FACE_ANALYSIS_MAX_EDGE, FACE_ANALYSIS_MAX_EDGE), Image.Resampling.LANCZOS)
                for face in self._detect_faces(tile):
                    x, y, width, height = face.bbox
                    tiled_faces.append(_DetectedFace(
                        bbox=(
                            (left + x * tile_width) / source.width,
                            (top + y * tile_height) / source.height,
                            width * tile_width / source.width,
                            height * tile_height / source.height,
                        ),
                        score=face.score,
                        keypoints=[
                            (
                                (left + point_x * tile_width) / source.width,
                                (top + point_y * tile_height) / source.height,
                            )
                            for point_x, point_y in face.keypoints
                        ],
                        detector=face.detector,
                    ))
        return _nms([*detected, *tiled_faces])

    @staticmethod
    def _landmark_bbox(landmarks: list[Any]) -> tuple[float, float, float, float]:
        xs = [float(item.x) for item in landmarks]
        ys = [float(item.y) for item in landmarks]
        left, right = min(xs), max(xs)
        top, bottom = min(ys), max(ys)
        return left, top, max(0.0, right - left), max(0.0, bottom - top)

    def _analyze_faces(self, source: Image.Image, analysis_image: Image.Image, detected: list[_DetectedFace]) -> list[dict[str, Any]]:
        landmark_entries: list[tuple[tuple[float, float, float, float], dict[str, float]]] = []
        if any(face.detector == "mediapipe_real" for face in detected):
            landmark_result = self._landmarker.detect(self._mp_image(analysis_image))
            blendshapes = list(landmark_result.face_blendshapes or [])
            for index, landmarks in enumerate(landmark_result.face_landmarks or []):
                shape_map = _blendshape_map(blendshapes[index]) if index < len(blendshapes) else {}
                landmark_entries.append((self._landmark_bbox(landmarks), shape_map))

        items: list[dict[str, Any]] = []
        for face in detected:
            x, y, width, height = face.bbox
            face_min_side = round(min(width * source.width, height * source.height))
            edge_margin = min(x, y, 1.0 - x - width, 1.0 - y - height)
            keypoint_outside = any(
                point_x <= 0.002 or point_x >= 0.998 or point_y <= 0.002 or point_y >= 0.998
                for point_x, point_y in face.keypoints
            )
            edge_crop_suspected = edge_margin < 0.05 * max(width, height) or keypoint_outside
            matched: tuple[tuple[float, float, float, float], dict[str, float]] | None = None
            if face.detector == "mediapipe_real" and landmark_entries:
                candidate = max(landmark_entries, key=lambda item: _iou(face.bbox, item[0]))
                if _iou(face.bbox, candidate[0]) >= 0.15:
                    matched = candidate
            clarity: dict[str, Any] | None = None
            if face_min_side >= FACE_LANDMARK_MIN_SIDE:
                face_sharpness = analyze_sharpness(_expanded_crop(source, face.bbox, face.keypoints))
                clarity = {
                    "score": face_sharpness["score"],
                    "severity": face_sharpness["severity"],
                    "hard_reject": face_sharpness["hard_reject"],
                }
            shape_map = matched[1] if matched else {}
            blink_left = float(shape_map.get("eyeBlinkLeft", 0.0))
            blink_right = float(shape_map.get("eyeBlinkRight", 0.0))
            review_eligible = face_min_side >= EYE_ANALYSIS_MIN_SIDE and face.score >= 0.80
            closed_eye_suspected = bool(
                face.detector == "mediapipe_real"
                and review_eligible
                and matched is not None
                and blink_left >= 0.75
                and blink_right >= 0.75
            )
            expression_keys = (
                "browDownLeft",
                "browDownRight",
                "jawOpen",
                "mouthFrownLeft",
                "mouthFrownRight",
                "mouthSmileLeft",
                "mouthSmileRight",
            )
            expression_vector = (
                {key: round(float(shape_map.get(key, 0.0)), 4) for key in expression_keys}
                if face.detector == "mediapipe_real"
                else {}
            )
            occlusion_suspected = bool(
                face.detector == "mediapipe_real"
                and review_eligible
                and face.score >= 0.90
                and matched is None
            )
            items.append({
                "bbox": [round(value, 5) for value in face.bbox],
                "detection_score": round(face.score, 4),
                "detector": face.detector,
                "min_side_px": face_min_side,
                "edge_crop_suspected": edge_crop_suspected,
                "clarity": clarity,
                "closed_eye_suspected": closed_eye_suspected,
                "occlusion_suspected": occlusion_suspected,
                "expression_attention": False,
                "expression_vector": expression_vector,
                "review_eligible": review_eligible,
                "capabilities": (
                    ["count", "bbox", "edge_crop", "clarity"]
                    if face.detector == "anime_yolov3"
                    else ["count", "bbox", "edge_crop", "clarity", "closed_eyes", "occlusion", "expression"]
                ),
            })
        return items

    def _analyze_pose(self, image: Image.Image) -> dict[str, Any] | None:
        if self._pose_landmarker is None:
            return None
        result = self._pose_landmarker.detect(self._mp_image(image))
        crop_suspected = 0
        for landmarks in result.pose_landmarks or []:
            important_indexes = (11, 12, 23, 24, 27, 28)
            important = [landmarks[index] for index in important_indexes]
            reliable = [item for item in important if float(getattr(item, "visibility", 0.0)) >= 0.5]
            if len(reliable) >= 4 and any(
                float(item.x) <= 0.02 or float(item.x) >= 0.98 or float(item.y) <= 0.02 or float(item.y) >= 0.98
                for item in reliable
            ):
                crop_suspected += 1
        return {
            "version": "mediapipe-pose-exp-v1",
            "experimental": True,
            "detected_pose_count": len(result.pose_landmarks or []),
            "body_crop_suspected_count": crop_suspected,
        }

    def analyze(self, image: Image.Image, *, content_profile: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {"available": False, "disabled": True, "version": self.version}
        with self._lock:
            profile = content_profile or {}
            graphic_profile = bool(
                profile.get("capture_kind") == "screenshot_or_graphic"
                or profile.get("visual_domain") in {"illustration", "mixed"}
            )
            analysis_image = self._analysis_image(image)
            detected: list[_DetectedFace] = []
            if not graphic_profile:
                self._load()
                if self._loaded:
                    detected = self._detect_faces_with_tiled_fallback(image, analysis_image)
            if graphic_profile or not detected:
                self._load_anime()
                if self._anime_net is not None:
                    try:
                        detected = _nms([*detected, *self._detect_anime_faces(analysis_image)])
                        self._anime_inference_error = None
                    except Exception as exc:  # noqa: BLE001
                        self._anime_inference_error = exc.__class__.__name__
            if not self._loaded and self._anime_net is None:
                return {
                    "available": False,
                    "version": self.version,
                    "fallback_reason": self._load_error or self._anime_load_error or "unavailable",
                    "anime_inference_error": self._anime_inference_error,
                }
            items = self._analyze_faces(image, analysis_image, detected)
            clarity_scores = [float(item["clarity"]["score"]) for item in items if item.get("clarity")]
            clarity_p20 = float(np.percentile(clarity_scores, 20)) if clarity_scores else 0.0
            result: dict[str, Any] = {
                "available": True,
                "version": self.version,
                "detected_count": len(items),
                "real_face_count": sum(item["detector"] == "mediapipe_real" for item in items),
                "anime_face_count": sum(item["detector"] == "anime_yolov3" for item in items),
                "coverage": "partial" if graphic_profile else "standard",
                "anime_fallback_reason": self._anime_load_error,
                "anime_inference_error": self._anime_inference_error,
                "analyzed_count": len(clarity_scores),
                "items": items,
                "aggregate": {
                    "clarity_p20": round(clarity_p20, 4),
                    "closed_eye_suspected_count": sum(bool(item["closed_eye_suspected"]) for item in items),
                    "edge_crop_suspected_count": sum(bool(item["edge_crop_suspected"]) for item in items),
                    "occlusion_suspected_count": sum(bool(item["occlusion_suspected"]) for item in items),
                    "high_value_closed_eye_count": sum(bool(item["closed_eye_suspected"] and item["review_eligible"]) for item in items),
                    "high_value_edge_crop_count": sum(bool(item["edge_crop_suspected"] and item["review_eligible"]) for item in items),
                    "high_value_occlusion_count": sum(bool(item["occlusion_suspected"] and item["review_eligible"]) for item in items),
                    "high_value_blur_count": sum(bool(
                        item["review_eligible"]
                        and (item.get("clarity") or {}).get("severity") == "severe"
                    ) for item in items),
                },
            }
            pose = self._analyze_pose(analysis_image) if self._loaded and not graphic_profile else None
            if pose is not None:
                result["pose"] = pose
            return result


class FaceFeatureExtractor(MediaPipeFaceAnalyzer):
    """Pipeline stage name for the local MediaPipe face and person extractor."""
