from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.album import Album
from app.models.export import Export
from app.repositories.album_repo import AlbumRepository
from app.repositories.export_repo import ExportRepository


async def require_album_access(session: AsyncSession, user, album_id: str) -> Album:
    album = await AlbumRepository(session).get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    if user.role != "admin" and album.user_id and album.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return album


async def require_export_access(session: AsyncSession, user, album_id: str, export_id: str) -> Export:
    export = await ExportRepository(session).get_export(album_id, export_id)
    if export is None:
        raise HTTPException(status_code=404, detail="export not found")
    album = await require_album_access(session, user, album_id)
    if export.album_id != album.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return export
