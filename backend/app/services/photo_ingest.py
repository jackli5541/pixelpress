from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ProcessedUploadImage:
    filename: str
    content_type: str
    content: bytes
    width: int | None
    height: int | None
    taken_at: datetime | None
    taken_timezone: str | None
    gps_latitude: float | None
    gps_longitude: float | None
    device_model: str | None


def process_uploaded_image(*, content: bytes, original_name: str, content_type: str) -> ProcessedUploadImage:
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()

    with Image.open(BytesIO(content)) as image:
        image.load()
        normalized_image = ImageOps.exif_transpose(image)
        metadata = _extract_metadata(image)
        normalized_content = content
        normalized_filename = original_name
        normalized_content_type = content_type or Image.MIME.get(image.format, "application/octet-stream")

        suffix = Path(original_name).suffix.lower()
        if suffix == ".heic":
            normalized_content = _encode_as_jpeg(normalized_image)
            normalized_filename = f"{Path(original_name).stem}.jpg"
            normalized_content_type = "image/jpeg"

        width, height = normalized_image.size
        return ProcessedUploadImage(
            filename=normalized_filename,
            content_type=normalized_content_type,
            content=normalized_content,
            width=width,
            height=height,
            taken_at=metadata["taken_at"],
            taken_timezone=metadata["taken_timezone"],
            gps_latitude=metadata["gps_latitude"],
            gps_longitude=metadata["gps_longitude"],
            device_model=metadata["device_model"],
        )


def _encode_as_jpeg(image) -> bytes:
    from PIL import Image

    output = BytesIO()
    converted = image.convert("RGB") if image.mode not in {"RGB", "L"} else image
    converted.save(output, format="JPEG", quality=92)
    return output.getvalue()


def _extract_metadata(image) -> dict[str, Any]:
    exif = image.getexif()
    if exif is None:
        return {
            "taken_at": None,
            "taken_timezone": None,
            "gps_latitude": None,
            "gps_longitude": None,
            "device_model": None,
        }

    tag_ids = _build_tag_lookup()
    taken_raw = exif.get(tag_ids.get("DateTimeOriginal")) or exif.get(tag_ids.get("DateTimeDigitized")) or exif.get(tag_ids.get("DateTime"))
    timezone_raw = exif.get(tag_ids.get("OffsetTimeOriginal")) or exif.get(tag_ids.get("OffsetTimeDigitized")) or exif.get(tag_ids.get("OffsetTime"))
    taken_at, taken_timezone = _parse_capture_datetime(taken_raw, timezone_raw)

    gps_info = None
    try:
        from PIL import ExifTags

        gps_info = exif.get_ifd(ExifTags.IFD.GPSInfo)
    except Exception:
        gps_info = exif.get(tag_ids.get("GPSInfo"))

    return {
        "taken_at": taken_at,
        "taken_timezone": taken_timezone,
        "gps_latitude": _parse_gps_coordinate(gps_info, ref_key=1, value_key=2),
        "gps_longitude": _parse_gps_coordinate(gps_info, ref_key=3, value_key=4),
        "device_model": _normalize_text(exif.get(tag_ids.get("Model"))),
    }


def _build_tag_lookup() -> dict[str, int]:
    from PIL import ExifTags

    return {name: tag_id for tag_id, name in ExifTags.TAGS.items()}


def _parse_capture_datetime(raw_value: Any, raw_offset: Any) -> tuple[datetime | None, str | None]:
    value = _normalize_text(raw_value)
    if not value:
        return None, None

    try:
        taken_at = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None, None

    timezone_label = _normalize_text(raw_offset)
    tzinfo = _parse_timezone_offset(timezone_label)
    if tzinfo is None:
        return taken_at.replace(tzinfo=UTC), None
    return taken_at.replace(tzinfo=tzinfo), timezone_label


def _parse_timezone_offset(value: str | None) -> timezone | None:
    if not value or len(value) != 6 or value[0] not in {"+", "-"} or value[3] != ":":
        return None

    try:
        hours = int(value[1:3])
        minutes = int(value[4:6])
    except ValueError:
        return None

    delta = timedelta(hours=hours, minutes=minutes)
    if value[0] == "-":
        delta = -delta
    return timezone(delta)


def _parse_gps_coordinate(gps_info: Any, *, ref_key: int, value_key: int) -> float | None:
    if not isinstance(gps_info, dict):
        return None

    ref = _normalize_text(gps_info.get(ref_key))
    values = gps_info.get(value_key)
    if not values or len(values) != 3:
        return None

    try:
        degrees = float(values[0])
        minutes = float(values[1])
        seconds = float(values[2])
    except Exception:
        return None

    coordinate = degrees + minutes / 60 + seconds / 3600
    if ref in {"S", "W"}:
        coordinate *= -1
    return round(coordinate, 7)


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip() or None
    text = str(value).strip()
    return text or None
