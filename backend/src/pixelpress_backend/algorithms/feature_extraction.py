from __future__ import annotations

import hashlib
import math
import threading
from typing import Any

import cv2
import numpy as np
from PIL import Image

try:
    import torch
    import clip
    from facenet_pytorch import MTCNN, InceptionResnetV1
    from ultralytics import YOLO
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class PerceptualHash:
    @staticmethod
    def compute(img: Image.Image) -> str:
        try:
            img = img.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
            pixels = np.array(img)
            avg = pixels.mean()
            bits = "".join(str(int(p > avg)) for p in pixels.flatten())
            return hashlib.md5(bits.encode()).hexdigest()
        except Exception:
            return ""

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        if len(hash1) != len(hash2):
            return len(hash1)
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


class ImageQualityAnalyzer:
    @staticmethod
    def analyze_sharpness(img: Image.Image) -> float:
        try:
            gray = np.array(img.convert("L"))
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            return float(np.var(laplacian))
        except Exception:
            return 0.0

    @staticmethod
    def analyze_exposure(img: Image.Image) -> float:
        try:
            gray = np.array(img.convert("L"))
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            total = gray.size
            dark = np.sum(hist[:30]) / total
            bright = np.sum(hist[225:]) / total
            return max(0, 1.0 - dark * 2 - bright * 2)
        except Exception:
            return 0.5

    @staticmethod
    def analyze_blur(img: Image.Image) -> float:
        try:
            gray = np.array(img.convert("L"))
            sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            edge_magnitude = np.sqrt(sobel_x**2 + sobel_y**2)
            return float(np.mean(edge_magnitude))
        except Exception:
            return 0.0

    @staticmethod
    def analyze_noise(img: Image.Image) -> float:
        try:
            gray = np.array(img.convert("L"))
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            noise = np.abs(gray.astype(float) - blurred.astype(float))
            return float(np.mean(noise))
        except Exception:
            return 0.0

    @staticmethod
    def compute_face_integrity(face_box: tuple[float, float, float, float], img_width: int, img_height: int) -> float:
        x, y, w, h = face_box
        margin = min(img_width, img_height) * 0.05
        if x < margin or y < margin:
            return 0.5
        if (x + w) > (img_width - margin) or (y + h) > (img_height - margin):
            return 0.5
        face_area = w * h
        img_area = img_width * img_height
        ratio = face_area / img_area
        if ratio < 0.01:
            return 0.3
        if ratio > 0.5:
            return 0.7
        return 0.8 + (ratio - 0.01) * 0.3 / 0.49


class YOLOFaceDetector:
    _lock = threading.Lock()
    _model = None

    @staticmethod
    def _get_model():
        if not TORCH_AVAILABLE:
            return None
        with YOLOFaceDetector._lock:
            if YOLOFaceDetector._model is None:
                try:
                    YOLOFaceDetector._model = YOLO("yolov8n-face.pt")
                except Exception:
                    YOLOFaceDetector._model = None
            return YOLOFaceDetector._model

    @staticmethod
    def detect(img: Image.Image) -> list[dict[str, Any]]:
        model = YOLOFaceDetector._get_model()
        if model is None:
            return YOLOFaceDetector._fallback_detect(img)
        try:
            results = model.predict(np.array(img), conf=0.5, verbose=False)
            boxes = []
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    boxes.append({
                        "x": float(x1),
                        "y": float(y1),
                        "width": float(x2 - x1),
                        "height": float(y2 - y1),
                        "confidence": float(box.conf[0])
                    })
            return boxes
        except Exception:
            return YOLOFaceDetector._fallback_detect(img)

    @staticmethod
    def _fallback_detect(img: Image.Image) -> list[dict[str, Any]]:
        return []


class YOLOSubjectDetector:
    _lock = threading.Lock()
    _model = None

    @staticmethod
    def _get_model():
        if not TORCH_AVAILABLE:
            return None
        with YOLOSubjectDetector._lock:
            if YOLOSubjectDetector._model is None:
                try:
                    YOLOSubjectDetector._model = YOLO("yolov8n.pt")
                except Exception:
                    YOLOSubjectDetector._model = None
            return YOLOSubjectDetector._model

    @staticmethod
    def detect(img: Image.Image) -> list[dict[str, Any]]:
        model = YOLOSubjectDetector._get_model()
        if model is None:
            return YOLOSubjectDetector._fallback_detect(img)
        try:
            results = model.predict(np.array(img), conf=0.4, verbose=False)
            boxes = []
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    boxes.append({
                        "x": float(x1),
                        "y": float(y1),
                        "width": float(x2 - x1),
                        "height": float(y2 - y1),
                        "confidence": float(box.conf[0]),
                        "class": int(box.cls[0])
                    })
            return boxes
        except Exception:
            return YOLOSubjectDetector._fallback_detect(img)

    @staticmethod
    def _fallback_detect(img: Image.Image) -> list[dict[str, Any]]:
        width, height = img.size
        return [{
            "x": width * 0.2,
            "y": height * 0.2,
            "width": width * 0.6,
            "height": height * 0.6,
            "confidence": 0.5,
            "class": 0
        }]


class CLIPEmbeddingGenerator:
    MODEL_VERSION = "clip-vit-b-32"
    _lock = threading.Lock()
    _model = None
    _preprocess = None
    _device = None

    @staticmethod
    def _get_model():
        if not TORCH_AVAILABLE:
            return None, None
        with CLIPEmbeddingGenerator._lock:
            if CLIPEmbeddingGenerator._model is None:
                try:
                    CLIPEmbeddingGenerator._device = "cuda" if torch.cuda.is_available() else "cpu"
                    CLIPEmbeddingGenerator._model, CLIPEmbeddingGenerator._preprocess = clip.load(
                        CLIPEmbeddingGenerator.MODEL_VERSION,
                        device=CLIPEmbeddingGenerator._device
                    )
                except Exception:
                    CLIPEmbeddingGenerator._model = None
            return CLIPEmbeddingGenerator._model, CLIPEmbeddingGenerator._preprocess

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
        width, height = img.size
        return [float(width % 256 / 255.0), float(height % 256 / 255.0)] + [0.0] * 510

    @staticmethod
    def cosine_similarity(emb1: list[float], emb2: list[float]) -> float:
        if len(emb1) != len(emb2):
            return 0.0
        dot = sum(a * b for a, b in zip(emb1, emb2))
        norm1 = math.sqrt(sum(a * a for a in emb1))
        norm2 = math.sqrt(sum(b * b for b in emb2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)


class FaceNetClusterer:
    _lock = threading.Lock()
    _mtcnn = None
    _resnet = None

    @staticmethod
    def _get_models():
        if not TORCH_AVAILABLE:
            return None, None
        with FaceNetClusterer._lock:
            if FaceNetClusterer._mtcnn is None:
                try:
                    FaceNetClusterer._mtcnn = MTCNN(image_size=160, margin=0, device="cuda" if torch.cuda.is_available() else "cpu")
                    FaceNetClusterer._resnet = InceptionResnetV1(pretrained="vggface2").eval().to(FaceNetClusterer._mtcnn.device)
                except Exception:
                    FaceNetClusterer._mtcnn = None
            return FaceNetClusterer._mtcnn, FaceNetClusterer._resnet

    @staticmethod
    def cluster_faces(images: dict[str, Image.Image]) -> dict[str, str]:
        mtcnn, resnet = FaceNetClusterer._get_models()
        if mtcnn is None:
            return FaceNetClusterer._fallback_cluster(images)
        try:
            face_embeddings = {}
            for photo_id, img in images.items():
                try:
                    face, prob = mtcnn(np.array(img), return_prob=True)
                    if face is not None:
                        face = face.unsqueeze(0).to(resnet.device)
                        with torch.no_grad():
                            embedding = resnet(face).cpu().numpy().flatten()
                        face_embeddings[photo_id] = embedding
                except Exception:
                    continue

            clusters = {}
            person_id = 0
            for photo_id, emb in face_embeddings.items():
                matched = False
                for pid, centroid in list(clusters.items()):
                    dist = np.linalg.norm(emb - centroid)
                    if dist < 1.0:
                        clusters[photo_id] = pid
                        matched = True
                        break
                if not matched:
                    new_id = f"person_{person_id}"
                    clusters[photo_id] = new_id
                    clusters[new_id] = emb
                    person_id += 1

            result = {}
            for photo_id in images.keys():
                result[photo_id] = clusters.get(photo_id, "")
            return result
        except Exception:
            return FaceNetClusterer._fallback_cluster(images)

    @staticmethod
    def _fallback_cluster(images: dict[str, Image.Image]) -> dict[str, str]:
        return {photo_id: "" for photo_id in images.keys()}


class U2NetSaliencyGenerator:
    _lock = threading.Lock()
    _model = None

    @staticmethod
    def _get_model():
        if not TORCH_AVAILABLE:
            return None
        with U2NetSaliencyGenerator._lock:
            if U2NetSaliencyGenerator._model is None:
                try:
                    from torchvision import models
                    U2NetSaliencyGenerator._model = models.segmentation.deeplabv3_resnet50(pretrained=True).eval()
                except Exception:
                    U2NetSaliencyGenerator._model = None
            return U2NetSaliencyGenerator._model

    @staticmethod
    def generate_saliency(img: Image.Image) -> str:
        model = U2NetSaliencyGenerator._get_model()
        if model is None:
            return ""
        try:
            from torchvision import transforms
            preprocess = transforms.Compose([
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
            input_tensor = preprocess(img).unsqueeze(0).to("cuda" if torch.cuda.is_available() else "cpu")
            with torch.no_grad():
                output = model(input_tensor)["out"][0]
            saliency = output.argmax(0).cpu().numpy()
            saliency_str = ",".join(str(int(v)) for v in saliency.flatten())
            return saliency_str[:1000]
        except Exception:
            return ""


class SceneTagGenerator:
    SCENE_LABELS = ["portrait", "landscape", "food", "architecture", "nature", "city", "animal", "event", "sports", "other"]

    @staticmethod
    def generate_tags(img: Image.Image) -> list[str]:
        try:
            width, height = img.size
            aspect_ratio = width / height
            tags = []
            if aspect_ratio > 1.5:
                tags.append("landscape")
            elif aspect_ratio < 0.67:
                tags.append("portrait")
            else:
                tags.append("other")
            return tags[:3]
        except Exception:
            return ["other"]


class DuplicateDetector:
    PERCEPTUAL_HASH_THRESHOLD = 8
    EMBEDDING_SIMILARITY_THRESHOLD = 0.92

    @staticmethod
    def find_duplicates(photo_features_list: list[dict[str, Any]]) -> list[list[str]]:
        groups = []
        visited = set()
        for i, features_i in enumerate(photo_features_list):
            if features_i.get("photo_id") in visited:
                continue
            group = [features_i["photo_id"]]
            visited.add(features_i["photo_id"])
            for j, features_j in enumerate(photo_features_list):
                if i == j or features_j.get("photo_id") in visited:
                    continue
                hash_i = features_i.get("perceptual_hash", "")
                hash_j = features_j.get("perceptual_hash", "")
                if hash_i and hash_j:
                    dist = PerceptualHash.hamming_distance(hash_i, hash_j)
                    if dist <= DuplicateDetector.PERCEPTUAL_HASH_THRESHOLD:
                        group.append(features_j["photo_id"])
                        visited.add(features_j["photo_id"])
                        continue
                emb_i = features_i.get("embedding", [])
                emb_j = features_j.get("embedding", [])
                if emb_i and emb_j:
                    sim = CLIPEmbeddingGenerator.cosine_similarity(emb_i, emb_j)
                    if sim >= DuplicateDetector.EMBEDDING_SIMILARITY_THRESHOLD:
                        group.append(features_j["photo_id"])
                        visited.add(features_j["photo_id"])
            if len(group) > 1:
                groups.append(group)
        return groups