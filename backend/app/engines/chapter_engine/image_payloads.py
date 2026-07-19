from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image, ImageOps

from app.ai.types import ImagePayload


def encode_image_payload(content: bytes, *, filename: str, max_edge: int, quality: int = 82) -> ImagePayload:
    with Image.open(BytesIO(content)) as source:
        source.load()
        image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return ImagePayload(
        media_type="image/jpeg",
        data_base64=base64.b64encode(output.getvalue()).decode("ascii"),
        width=image.width,
        height=image.height,
        filename=filename,
    )
