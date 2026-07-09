from __future__ import annotations

import argparse
import mimetypes
from io import BytesIO
from pathlib import Path

from minio.error import S3Error
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.storage.file_store import get_uploads_root
from app.storage.minio_file_storage import MinioFileStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy local photo files to MinIO.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect only; do not upload or update the database.")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N photo rows.")
    parser.add_argument("--photo-id", dest="photo_ids", action="append", default=[], help="Only migrate a specific photo id. Repeatable.")
    parser.add_argument("--album-id", dest="album_ids", action="append", default=[], help="Only migrate a specific album id. Repeatable.")
    parser.add_argument("--delete-local", action="store_true", help="Delete the local file after a successful upload.")
    parser.add_argument("--overwrite", action="store_true", help="Always upload even if the MinIO object already exists.")
    return parser.parse_args()


def build_query(args: argparse.Namespace) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict[str, object] = {}
    if args.photo_ids:
        clauses.append("id = ANY(:photo_ids)")
        params["photo_ids"] = args.photo_ids
    if args.album_ids:
        clauses.append("album_id = ANY(:album_ids)")
        params["album_ids"] = args.album_ids
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = " LIMIT :limit" if args.limit else ""
    if args.limit:
        params["limit"] = args.limit
    sql = (
        "SELECT id, album_id, filename, content_type, size, storage_key, url "
        f"FROM photos {where_sql} ORDER BY album_id, id{limit_sql}"
    )
    return sql, params


def resolve_local_path(uploads_root: Path, album_id: str, filename: str, storage_key: str | None) -> Path | None:
    candidates: list[Path] = []
    if storage_key:
        candidates.append(uploads_root / storage_key)
        candidates.append(uploads_root / album_id / Path(storage_key).name)
    candidates.append(uploads_root / album_id / filename)

    seen: set[Path] = set()
    for candidate in candidates:
        normalized = candidate.resolve()
        if normalized in seen:
            continue
        seen.add(normalized)
        if normalized.exists() and normalized.is_file():
            return normalized
    return None


def canonical_storage_key(album_id: str, source_path: Path, storage_key: str | None) -> str:
    if storage_key and storage_key.startswith("albums/"):
        return storage_key
    return f"albums/{album_id}/photos/{source_path.name}"


def object_exists(storage: MinioFileStorage, object_name: str) -> bool:
    try:
        storage.client.stat_object(storage.bucket, object_name)
        return True
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            return False
        raise


def main() -> int:
    args = parse_args()
    settings = get_settings()
    uploads_root = get_uploads_root()
    storage = MinioFileStorage()
    engine = create_engine(settings.database_url, future=True)

    stats = {
        "scanned": 0,
        "uploaded": 0,
        "already_present": 0,
        "missing_local": 0,
        "db_updated": 0,
        "deleted_local": 0,
    }

    sql, params = build_query(args)
    update_stmt = text(
        "UPDATE photos SET storage_key = :storage_key, url = :url, size = :size, content_type = :content_type WHERE id = :id"
    )

    try:
        with engine.begin() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
            for row in rows:
                stats["scanned"] += 1
                photo_id = row["id"]
                album_id = row["album_id"]
                source_path = resolve_local_path(uploads_root, album_id, row["filename"], row["storage_key"])
                if source_path is None:
                    stats["missing_local"] += 1
                    print(f"[missing] photo={photo_id} album={album_id} storage_key={row['storage_key']}")
                    continue

                content_type = row["content_type"] or mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
                target_key = canonical_storage_key(album_id, source_path, row["storage_key"])
                url = f"/api/v1/albums/{album_id}/photos/{photo_id}/content"
                target_exists = object_exists(storage, target_key)
                uploaded_now = False

                if target_exists and not args.overwrite:
                    stats["already_present"] += 1
                    print(f"[skip] object exists for photo={photo_id} key={target_key}")
                else:
                    if args.dry_run:
                        print(f"[dry-run] upload photo={photo_id} from={source_path} to={target_key}")
                    else:
                        payload = source_path.read_bytes()
                        storage.client.put_object(
                            storage.bucket,
                            target_key,
                            BytesIO(payload),
                            length=len(payload),
                            content_type=content_type,
                        )
                        stats["uploaded"] += 1
                        uploaded_now = True
                        print(f"[uploaded] photo={photo_id} key={target_key}")

                needs_db_update = (
                    row["storage_key"] != target_key
                    or row["url"] != url
                    or row["size"] != source_path.stat().st_size
                    or row["content_type"] != content_type
                )
                if needs_db_update:
                    if args.dry_run:
                        print(f"[dry-run] update db photo={photo_id} storage_key={target_key}")
                    else:
                        conn.execute(
                            update_stmt,
                            {
                                "id": photo_id,
                                "storage_key": target_key,
                                "url": url,
                                "size": source_path.stat().st_size,
                                "content_type": content_type,
                            },
                        )
                        stats["db_updated"] += 1

                if args.delete_local and not args.dry_run and (target_exists or uploaded_now):
                    source_path.unlink(missing_ok=True)
                    stats["deleted_local"] += 1
    finally:
        engine.dispose()

    print("Summary:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0 if stats["missing_local"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
