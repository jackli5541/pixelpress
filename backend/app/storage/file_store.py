from pathlib import Path

from app.core.config import get_settings


def get_uploads_root() -> Path:
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    uploads_root = backend_root / settings.uploads_dir
    uploads_root.mkdir(parents=True, exist_ok=True)
    return uploads_root


def get_album_upload_dir(album_id: str) -> Path:
    album_dir = get_uploads_root() / album_id
    album_dir.mkdir(parents=True, exist_ok=True)
    return album_dir
