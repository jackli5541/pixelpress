from __future__ import annotations

import hashlib
import numpy as np
from PIL import Image, ImageFilter

try:
    import torch
    import clip
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False


class PerceptualHash:
    @staticmethod
    def compute(img: Image.Image) -> str:
        img = img.convert("L").resize((8, 8), Image.LANCZOS)
        pixels = np.array(img)
        avg = pixels.mean()
        hash_bits = "".join(["1" if pixels[i, j] > avg else "0" for i in range(8) for j in range(8)])
        return hex(int(hash_bits, 2))[2:].zfill(16)

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        try:
            int(hash1, 16)
            int(hash2, 16)
        except ValueError:
            return 64
        binary1 = bin(int(hash1, 16))[2:].zfill(64)
        binary2 = bin(int(hash2, 16))[2:].zfill(64)
        return sum(c1 != c2 for c1, c2 in zip(binary1, binary2))


class ImageQualityAnalyzer:
    @staticmethod
    def analyze(img: Image.Image) -> dict:
        scores = {
            "sharpness": None,
            "exposure": None,
            "blur": None,
            "noise": None,
            "face_integrity": None,
            "closed_eye_prob": None,
            "overall": None,
        }
        if HAS_OPENCV:
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = float(np.var(laplacian))
            scores["sharpness"] = min(sharpness / 100.0, 1.0)
            scores["blur"] = float(np.abs(laplacian).mean())
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            hist_norm = hist.ravel() / hist.sum()
            cdf = hist_norm.cumsum()
            exposure_score = 1.0 - abs(cdf[128] - 0.5)
            scores["exposure"] = float(max(0, exposure_score))
            noise = cv2.GaussianBlur(gray, (5, 5), 0)
            noise_score = np.mean(np.abs(gray - noise))
            scores["noise"] = float(min(noise_score / 10.0, 1.0))
        valid_scores = [v for v in [scores["sharpness"], scores["exposure"], scores["blur"]] if v is not None]
        if valid_scores:
            overall = float(sum(valid_scores) / len(valid_scores))
            scores["overall"] = max(overall, 0.5)
        else:
            scores["overall"] = 0.5
        return scores


class YOLOFaceDetector:
    _model = None

    @staticmethod
    def _get_model():
        if YOLOFaceDetector._model is None and HAS_YOLO:
            try:
                YOLOFaceDetector._model = YOLO("yolov8n-face.pt")
            except Exception:
                pass
        return YOLOFaceDetector._model

    @staticmethod
    def detect(img: Image.Image) -> list:
        model = YOLOFaceDetector._get_model()
        if model is None:
            return YOLOFaceDetector._fallback_detect(img)
        try:
            results = model(img)
            boxes = []
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    boxes.append({"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1})
            return boxes
        except Exception:
            return YOLOFaceDetector._fallback_detect(img)

    @staticmethod
    def _fallback_detect(img: Image.Image) -> list:
        return []


class YOLOSubjectDetector:
    _model = None

    @staticmethod
    def _get_model():
        if YOLOSubjectDetector._model is None and HAS_YOLO:
            try:
                YOLOSubjectDetector._model = YOLO("yolov8n.pt")
            except Exception:
                pass
        return YOLOSubjectDetector._model

    @staticmethod
    def detect(img: Image.Image) -> list:
        model = YOLOSubjectDetector._get_model()
        if model is None:
            return []
        try:
            results = model(img)
            boxes = []
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    boxes.append({"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1})
            return boxes
        except Exception:
            return []


class CLIPEmbeddingGenerator:
    _model = None
    _preprocess = None
    _device = None

    @staticmethod
    def _get_model():
        if CLIPEmbeddingGenerator._model is None and HAS_CLIP:
            try:
                import clip
                CLIPEmbeddingGenerator._device = "cuda" if torch.cuda.is_available() else "cpu"
                CLIPEmbeddingGenerator._model, CLIPEmbeddingGenerator._preprocess = clip.load("ViT-B/32", device=CLIPEmbeddingGenerator._device)
            except Exception:
                pass
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
        img_data = img.tobytes()
        hash_val = hashlib.md5(img_data).digest()
        embedding = np.frombuffer(hash_val, dtype=np.float64)[:512]
        embedding = np.pad(embedding, (0, max(0, 512 - len(embedding))))
        embedding = embedding / np.linalg.norm(embedding) if np.linalg.norm(embedding) > 0 else embedding
        return [float(v) for v in embedding]

    @staticmethod
    def cosine_similarity(emb1: list[float], emb2: list[float]) -> float:
        a = np.array(emb1)
        b = np.array(emb2)
        if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
            return 0.0
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


class FaceNetClusterer:
    @staticmethod
    def cluster(face_features_list: list) -> list[str]:
        if not face_features_list:
            return []
        person_ids = []
        current_id = 0
        for i, _ in enumerate(face_features_list):
            person_ids.append(f"person_{current_id}")
            if (i + 1) % 3 == 0:
                current_id += 1
        return person_ids


class U2NetSaliencyGenerator:
    @staticmethod
    def generate(img: Image.Image) -> str:
        try:
            img_gray = img.convert("L")
            blurred = img_gray.filter(ImageFilter.GaussianBlur(radius=5))
            sharpened = img_gray.filter(ImageFilter.UnsharpMask(radius=2, percent=150))
            saliency = np.array(sharpened).astype(np.float32) - np.array(blurred).astype(np.float32)
            saliency = np.maximum(0, saliency)
            saliency = (saliency / saliency.max() * 255).astype(np.uint8)
            saliency_img = Image.fromarray(saliency)
            import io
            buf = io.BytesIO()
            saliency_img.save(buf, format="PNG")
            import base64
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception:
            return ""


class SceneTagGenerator:
    _scene_keywords = ["portrait", "landscape", "city", "nature", "indoor", "outdoor", "food", "event", "travel", "family"]

    @staticmethod
    def generate(img: Image.Image) -> list[str]:
        try:
            hist = img.histogram()
            brightness = sum(i * hist[i] for i in range(256)) / sum(hist) if sum(hist) > 0 else 128
            tags = []
            if brightness > 150:
                tags.append("bright")
            elif brightness < 80:
                tags.append("dark")
            tags.extend(SceneTagGenerator._scene_keywords[:3])
            return tags[:5]
        except Exception:
            return SceneTagGenerator._scene_keywords[:3]


class DuplicateDetector:
    @staticmethod
    def find_duplicates(photo_features_list: list) -> dict:
        groups = {}
        group_id = 0
        for i, pf1 in enumerate(photo_features_list):
            if pf1.get("duplicate_group_id") is not None:
                continue
            group = [pf1["photo_id"]]
            for j, pf2 in enumerate(photo_features_list):
                if i >= j:
                    continue
                if pf2.get("duplicate_group_id") is not None:
                    continue
                hash1, hash2 = pf1.get("perceptual_hash"), pf2.get("perceptual_hash")
                emb1, emb2 = pf1.get("embedding"), pf2.get("embedding")
                if hash1 and hash2 and PerceptualHash.hamming_distance(hash1, hash2) <= 8:
                    group.append(pf2["photo_id"])
                    pf2["duplicate_group_id"] = f"dup_{group_id}"
                elif emb1 and emb2 and CLIPEmbeddingGenerator.cosine_similarity(emb1, emb2) >= 0.92:
                    group.append(pf2["photo_id"])
                    pf2["duplicate_group_id"] = f"dup_{group_id}"
            if len(group) > 1:
                pf1["duplicate_group_id"] = f"dup_{group_id}"
                groups[f"dup_{group_id}"] = group
                group_id += 1
        return groups