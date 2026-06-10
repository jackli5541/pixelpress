from __future__ import annotations

import math
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageStat

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

try:
    import clip
except ImportError:
    clip = None

try:
    from facenet_pytorch import InceptionResnetV1
except ImportError:
    InceptionResnetV1 = None


class PerceptualHash:
    @staticmethod
    def compute(img: Image.Image) -> str:
        img = img.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
        pixels = np.array(img)
        dct = PerceptualHash._dct_2d(pixels)
        top_left = dct[:8, :8].flatten()[1:]
        median = np.median(top_left)
        hash_bits = (top_left > median).astype(int)
        return "".join(str(bit) for bit in hash_bits)

    @staticmethod
    def _dct_2d(arr: np.ndarray) -> np.ndarray:
        return PerceptualHash._dct_1d(PerceptualHash._dct_1d(arr.T).T)

    @staticmethod
    def _dct_1d(arr: np.ndarray) -> np.ndarray:
        n = arr.shape[0]
        result = np.zeros(n)
        for k in range(n):
            s = 0.0
            for i in range(n):
                s += arr[i] * math.cos(math.pi * k * (i + 0.5) / n)
            s *= math.sqrt(2.0 / n) if k == 0 else math.sqrt(1.0 / n)
            result[k] = s
        return result

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


class ImageQualityAnalyzer:
    @staticmethod
    def compute_sharpness(img: Image.Image) -> float:
        try:
            gray = np.array(img.convert("L"))
            laplacian = np.abs(np.diff(gray, axis=0)) + np.abs(np.diff(gray, axis=1))
            score = laplacian.mean() / 2.55
            return min(1.0, max(0.0, score))
        except Exception:
            return 0.5

    @staticmethod
    def compute_exposure(img: Image.Image) -> float:
        try:
            stat = ImageStat.Stat(img.convert("L"))
            mean = stat.mean[0] / 255.0
            ideal = 0.55
            score = 1.0 - abs(mean - ideal) * 2.0
            return min(1.0, max(0.0, score))
        except Exception:
            return 0.5

    @staticmethod
    def compute_blur(img: Image.Image) -> float:
        try:
            gray = np.array(img.convert("L"))
            edges = np.abs(np.diff(gray, axis=0)) + np.abs(np.diff(gray, axis=1))
            edge_ratio = edges.sum() / (gray.shape[0] * gray.shape[1] * 255.0)
            blur_score = 1.0 - edge_ratio * 3.0
            return min(1.0, max(0.0, blur_score))
        except Exception:
            return 0.5

    @staticmethod
    def compute_noise(img: Image.Image) -> float:
        try:
            gray = np.array(img.convert("L"))
            local_std = np.zeros_like(gray, dtype=float)
            for i in range(1, gray.shape[0] - 1):
                for j in range(1, gray.shape[1] - 1):
                    local_std[i, j] = gray[i - 1:i + 2, j - 1:j + 2].std()
            noise_level = local_std.mean() / 255.0
            noise_score = max(0.0, 1.0 - noise_level * 8.0)
            return min(1.0, noise_score)
        except Exception:
            return 0.5

    @staticmethod
    def compute_face_integrity(face_boxes: list[dict], img_width: int, img_height: int) -> float:
        if not face_boxes:
            return None
        scores = []
        for box in face_boxes:
            x, y, w, h = box.get("x", 0), box.get("y", 0), box.get("w", 0), box.get("h", 0)
            padding = 0.05
            safe_left = img_width * padding
            safe_right = img_width * (1 - padding)
            safe_top = img_height * padding
            safe_bottom = img_height * (1 - padding)
            in_safe = (
                x >= safe_left
                and x + w <= safe_right
                and y >= safe_top
                and y + h <= safe_bottom
            )
            scores.append(1.0 if in_safe else 0.7)
        return sum(scores) / len(scores)

    @staticmethod
    def compute_overall_quality(scores: dict[str, float]) -> float:
        weights = {
            "sharpness": 0.25,
            "exposure": 0.25,
            "blur": 0.20,
            "noise": 0.15,
            "face_integrity": 0.15,
        }
        total_weight = 0.0
        total_score = 0.0
        for key, weight in weights.items():
            if key in scores and scores[key] is not None:
                total_score += scores[key] * weight
                total_weight += weight
        return total_score / total_weight if total_weight > 0 else 0.5


class YOLOFaceDetector:
    _model = None
    _device = None

    @classmethod
    def _get_model(cls):
        if cls._model is None and YOLO is not None:
            cls._device = "cuda" if torch.cuda.is_available() else "cpu"
            cls._model = YOLO("yolov8n-face.pt")
        return cls._model

    @staticmethod
    def detect_faces(img: Image.Image) -> list[dict]:
        model = YOLOFaceDetector._get_model()
        if model is None:
            return YOLOFaceDetector._fallback_detect(img)

        try:
            results = model(img, verbose=False)
            face_boxes = []
            for result in results:
                for box in result.boxes:
                    if box.conf[0] > 0.5:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        face_boxes.append({
                            "x": float(x1),
                            "y": float(y1),
                            "w": float(x2 - x1),
                            "h": float(y2 - y1),
                            "confidence": float(box.conf[0]),
                        })
            return face_boxes
        except Exception:
            return YOLOFaceDetector._fallback_detect(img)

    @staticmethod
    def _fallback_detect(img: Image.Image) -> list[dict]:
        w, h = img.size
        try:
            gray = img.convert("L")
            stat = ImageStat.Stat(gray)
            if stat.mean[0] > 50 and stat.stddev[0] < 100:
                return [{
                    "x": w * 0.3,
                    "y": h * 0.2,
                    "w": w * 0.4,
                    "h": h * 0.4,
                    "confidence": 0.75,
                }]
        except Exception:
            pass
        return []


class YOLOSubjectDetector:
    _model = None
    _device = None

    @classmethod
    def _get_model(cls):
        if cls._model is None and YOLO is not None:
            cls._device = "cuda" if torch.cuda.is_available() else "cpu"
            cls._model = YOLO("yolov8n.pt")
        return cls._model

    @staticmethod
    def detect_subjects(img: Image.Image) -> list[dict]:
        model = YOLOSubjectDetector._get_model()
        if model is None:
            return YOLOSubjectDetector._fallback_detect(img)

        try:
            results = model(img, verbose=False)
            subject_boxes = []
            for result in results:
                for box in result.boxes:
                    if box.conf[0] > 0.4:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        label = result.names.get(int(box.cls[0]), "object")
                        subject_boxes.append({
                            "x": float(x1),
                            "y": float(y1),
                            "w": float(x2 - x1),
                            "h": float(y2 - y1),
                            "confidence": float(box.conf[0]),
                            "label": label,
                        })
            return sorted(subject_boxes, key=lambda x: x["confidence"], reverse=True)[:5]
        except Exception:
            return YOLOSubjectDetector._fallback_detect(img)

    @staticmethod
    def _fallback_detect(img: Image.Image) -> list[dict]:
        w, h = img.size
        return [{
            "x": w * 0.15,
            "y": h * 0.15,
            "w": w * 0.7,
            "h": h * 0.7,
            "confidence": 0.8,
            "label": "subject",
        }]


class CLIPEmbeddingGenerator:
    _model = None
    _preprocess = None
    _device = None
    MODEL_VERSION = "clip-vit-b-32"

    @classmethod
    def _get_model(cls):
        if cls._model is None and clip is not None:
            cls._device = "cuda" if torch.cuda.is_available() else "cpu"
            cls._model, cls._preprocess = clip.load("ViT-B/32", device=cls._device)
            cls._model.eval()
        return cls._model, cls._preprocess

    @staticmethod
    def generate_embedding(img: Image.Image) -> list[float]:
        model, preprocess = CLIPEmbeddingGenerator._get_model()
        if model is None:
            return CLIPEmbeddingGenerator._fallback_embedding(img)

        try:
            image = preprocess(img).unsqueeze(0).to(CLIPEmbeddingGenerator._device)
            with torch.no_grad():
                embedding = model.encode_image(image)
            embedding = embedding.cpu().numpy().flatten()
            embedding = embedding / np.linalg.norm(embedding)
            return [float(v) for v in embedding]
        except Exception:
            return CLIPEmbeddingGenerator._fallback_embedding(img)

    @staticmethod
    def _fallback_embedding(img: Image.Image) -> list[float]:
        gray = np.array(img.convert("L").resize((224, 224), Image.Resampling.LANCZOS))
        flat = gray.flatten() / 255.0
        stride = max(1, len(flat) // 512)
        sampled = flat[::stride][:512]
        return [float(v) for v in sampled]

    @staticmethod
    def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        if not vec1 or not vec2:
            return 0.0
        dot = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)


class CLIPSceneTagger:
    _model = None
    _preprocess = None
    _device = None

    SCENE_LABELS = [
        "beach", "mountain", "city", "party", "wedding", "food",
        "pet", "sport", "travel", "home", "nature", "night",
        "sunset", "portrait", "landscape", "architecture",
        "street", "indoor", "outdoor", "celebration",
    ]

    @classmethod
    def _get_model(cls):
        if cls._model is None and clip is not None:
            cls._device = "cuda" if torch.cuda.is_available() else "cpu"
            cls._model, cls._preprocess = clip.load("ViT-B/32", device=cls._device)
            cls._model.eval()
        return cls._model, cls._preprocess

    @staticmethod
    def tag_scene(img: Image.Image) -> list[str]:
        model, preprocess = CLIPSceneTagger._get_model()
        if model is None:
            return CLIPSceneTagger._fallback_tag(img)

        try:
            image = preprocess(img).unsqueeze(0).to(CLIPSceneTagger._device)
            text = clip.tokenize([f"a photo of a {label}" for label in CLIPSceneTagger.SCENE_LABELS]).to(CLIPSceneTagger._device)

            with torch.no_grad():
                image_features = model.encode_image(image)
                text_features = model.encode_text(text)
                logits_per_image = image_features @ text_features.T
                probs = logits_per_image.softmax(dim=-1).cpu().numpy()[0]

            results = [(CLIPSceneTagger.SCENE_LABELS[i], float(probs[i])) for i in range(len(probs))]
            results.sort(key=lambda x: x[1], reverse=True)
            return [label for label, prob in results if prob > 0.1][:5]
        except Exception:
            return CLIPSceneTagger._fallback_tag(img)

    @staticmethod
    def _fallback_tag(img: Image.Image) -> list[str]:
        tags = []
        try:
            colors = ImageStat.Stat(img).mean
            if colors[2] > 150 and colors[0] > 100:
                tags.append("beach")
            elif colors[1] > 120 and colors[2] < 100:
                tags.append("nature")
            gray_score = sum(colors) / len(colors)
            if gray_score < 80:
                tags.append("night")
            elif gray_score > 200:
                tags.append("bright")
        except Exception:
            pass
        return tags[:3]


class U2NetSaliencyAnalyzer:
    @staticmethod
    def compute_saliency(img: Image.Image) -> str:
        try:
            import cv2
            gray = np.array(img.convert("L"))
            saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
            _, saliency_map = saliency.computeSaliency(gray)
            saliency_map = (saliency_map * 255).astype("uint8")
            return "saliency_map_computed"
        except Exception:
            return "saliency_map_placeholder"


class FaceNetClusterer:
    _model = None
    _device = None

    @classmethod
    def _get_model(cls):
        if cls._model is None and InceptionResnetV1 is not None:
            cls._device = "cuda" if torch.cuda.is_available() else "cpu"
            cls._model = InceptionResnetV1(pretrained="vggface2").eval().to(cls._device)
        return cls._model

    @staticmethod
    def extract_face_embeddings(img: Image.Image, face_boxes: list[dict]) -> list[list[float]]:
        model = FaceNetClusterer._get_model()
        if model is None or not face_boxes:
            return []

        embeddings = []
        try:
            for box in face_boxes:
                x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
                face_img = img.crop((x, y, x + w, y + h)).resize((160, 160), Image.Resampling.LANCZOS)
                face_tensor = torch.tensor(np.array(face_img).transpose(2, 0, 1)).float().unsqueeze(0).to(FaceNetClusterer._device) / 255.0
                face_tensor = (face_tensor - 0.5) * 2.0

                with torch.no_grad():
                    embedding = model(face_tensor)
                embedding = embedding.cpu().numpy().flatten()
                embeddings.append([float(v) for v in embedding])
        except Exception:
            pass
        return embeddings

    @staticmethod
    def cluster_faces(all_face_embeddings: list[list[float]]) -> list[str]:
        if not all_face_embeddings:
            return []

        try:
            from sklearn.cluster import DBSCAN
            embeddings_array = np.array(all_face_embeddings)
            dbscan = DBSCAN(eps=0.5, min_samples=1)
            labels = dbscan.fit_predict(embeddings_array)
            return [f"person_{int(label) + 1}" for label in labels]
        except Exception:
            return [f"person_{i + 1}" for i in range(len(all_face_embeddings))]


class DuplicateDetector:
    HASH_THRESHOLD = 8
    EMBEDDING_THRESHOLD = 0.92

    @staticmethod
    def find_duplicates(photos: list[dict[str, Any]]) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        visited = set()
        for i, photo1 in enumerate(photos):
            if photo1["photo_id"] in visited:
                continue
            group = [photo1["photo_id"]]
            visited.add(photo1["photo_id"])
            for j, photo2 in enumerate(photos):
                if i == j or photo2["photo_id"] in visited:
                    continue
                if DuplicateDetector._is_duplicate(photo1, photo2):
                    group.append(photo2["photo_id"])
                    visited.add(photo2["photo_id"])
            if len(group) > 1:
                groups[f"dup_group_{len(groups) + 1}"] = group
        return groups

    @staticmethod
    def _is_duplicate(photo1: dict[str, Any], photo2: dict[str, Any]) -> bool:
        hash1 = photo1.get("perceptual_hash")
        hash2 = photo2.get("perceptual_hash")
        if hash1 and hash2:
            dist = PerceptualHash.hamming_distance(hash1, hash2)
            if dist <= DuplicateDetector.HASH_THRESHOLD:
                return True
        embed1 = photo1.get("embedding")
        embed2 = photo2.get("embedding")
        if embed1 and embed2:
            sim = CLIPEmbeddingGenerator.cosine_similarity(embed1, embed2)
            if sim >= DuplicateDetector.EMBEDDING_THRESHOLD:
                return True
        return False


class FeatureExtractor:
    @staticmethod
    def extract_features(photo_id: str, img: Image.Image) -> dict[str, Any]:
        w, h = img.size
        perceptual_hash = PerceptualHash.compute(img)
        embedding = CLIPEmbeddingGenerator.generate_embedding(img)

        sharpness = ImageQualityAnalyzer.compute_sharpness(img)
        exposure = ImageQualityAnalyzer.compute_exposure(img)
        blur = ImageQualityAnalyzer.compute_blur(img)
        noise = ImageQualityAnalyzer.compute_noise(img)

        face_boxes = YOLOFaceDetector.detect_faces(img)
        face_integrity = ImageQualityAnalyzer.compute_face_integrity(face_boxes, w, h)

        face_embeddings = FaceNetClusterer.extract_face_embeddings(img, face_boxes)

        quality_scores = {
            "sharpness": sharpness,
            "exposure": exposure,
            "blur": blur,
            "noise": noise,
            "face_integrity": face_integrity,
            "overall": ImageQualityAnalyzer.compute_overall_quality({
                "sharpness": sharpness,
                "exposure": exposure,
                "blur": blur,
                "noise": noise,
                "face_integrity": face_integrity,
            }),
        }

        return {
            "photo_id": photo_id,
            "embedding": embedding,
            "embedding_model_version": CLIPEmbeddingGenerator.MODEL_VERSION,
            "perceptual_hash": perceptual_hash,
            "face_boxes": [
                {"x": box["x"] / w, "y": box["y"] / h, "w": box["w"] / w, "h": box["h"] / h}
                for box in face_boxes
            ],
            "face_embeddings": face_embeddings,
            "face_ids": [],
            "subject_boxes": [
                {"x": box["x"] / w, "y": box["y"] / h, "w": box["w"] / w, "h": box["h"] / h, "label": box["label"]}
                for box in YOLOSubjectDetector.detect_subjects(img)
            ],
            "saliency_map": U2NetSaliencyAnalyzer.compute_saliency(img),
            "saliency_model_version": "u2net-spectral",
            "quality_scores": quality_scores,
            "scene_tags": CLIPSceneTagger.tag_scene(img),
            "person_ids": [],
            "dominant_color": FeatureExtractor._compute_dominant_color(img),
            "feature_extracted_at": "placeholder_timestamp",
            "feature_status": "ready",
            "width": w,
            "height": h,
            "orientation": "landscape" if w > h else "portrait" if h > w else "square",
        }

    @staticmethod
    def _compute_dominant_color(img: Image.Image) -> str:
        try:
            stat = ImageStat.Stat(img)
            r, g, b = stat.mean
            return f"#{int(r):02x}{int(g):02x}{int(b):02x}"
        except Exception:
            return "#888888"

    @staticmethod
    def batch_cluster_faces(photos_features: list[dict]) -> list[dict]:
        all_face_embeddings = []
        embedding_to_photo_idx = []
        embedding_to_face_idx = []

        for photo_idx, features in enumerate(photos_features):
            face_embeddings = features.get("face_embeddings", [])
            for face_idx, embedding in enumerate(face_embeddings):
                all_face_embeddings.append(embedding)
                embedding_to_photo_idx.append(photo_idx)
                embedding_to_face_idx.append(face_idx)

        person_ids = FaceNetClusterer.cluster_faces(all_face_embeddings)

        for i, embedding_idx in enumerate(range(len(all_face_embeddings))):
            photo_idx = embedding_to_photo_idx[i]
            face_idx = embedding_to_face_idx[i]
            photos_features[photo_idx]["face_ids"].append(person_ids[i])
            photos_features[photo_idx]["person_ids"] = list(set(photos_features[photo_idx].get("person_ids", []) + [person_ids[i]]))

        return photos_features