from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import time

import requests


MODEL_URL = "https://storage.googleapis.com/ailia-models/anime-face-detector/anime-face_yolov3.onnx"
MODEL_SIZE = 246_055_481
SOURCE_SHA256 = "b5eeaf2fa7f18aeead73a4e0884e871d6961a63d9cf1e143ef48c58aa35f885c"
MODEL_SHA256 = "a5463535d733c3edcf90c4578fc5a281bac82e148d23b05e12f8abacaae24c51"
DEFAULT_DESTINATION = Path(__file__).resolve().parents[1] / "models" / "cleaning" / "anime-face_yolov3.onnx"


def _digest(path: Path) -> str:
    result = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def _download(destination: Path, *, chunk_size: int) -> None:
    total = MODEL_SIZE
    with destination.open("w+b") as output:
        output.truncate(total)
        for start in range(0, total, chunk_size):
            end = min(total - 1, start + chunk_size - 1)
            for attempt in range(5):
                try:
                    response = requests.get(
                        MODEL_URL,
                        headers={"Range": f"bytes={start}-{end}", "Connection": "close"},
                        timeout=(10, 15),
                    )
                    response.raise_for_status()
                    content = response.content
                    if response.status_code != 206 or len(content) != end - start + 1:
                        raise RuntimeError("model server returned an invalid byte range")
                    output.seek(start)
                    output.write(content)
                    output.flush()
                    break
                except Exception:  # noqa: BLE001
                    if attempt == 4:
                        raise
                    time.sleep(2 ** attempt)
            print(f"downloaded {end + 1}/{total}", flush=True)


def fetch(destination: Path, *, chunk_size: int = 1024 * 1024) -> None:
    from onnx import utils

    destination.parent.mkdir(parents=True, exist_ok=True)
    source = destination.with_suffix(destination.suffix + ".source")
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        _download(source, chunk_size=chunk_size)
        source_digest = _digest(source)
        if source_digest != SOURCE_SHA256:
            raise RuntimeError(f"source model checksum mismatch: {source_digest}")
        utils.extract_model(
            str(source),
            str(partial),
            ["input"],
            ["1252", "1253", "1254"],
            check_model=False,
        )
        digest = _digest(partial)
        if digest != MODEL_SHA256:
            raise RuntimeError(f"prepared model checksum mismatch: {digest}")
        partial.replace(destination)
        print(f"sha256={digest}")
    finally:
        source.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    fetch(args.destination)


if __name__ == "__main__":
    main()
