from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PagePhoto(Base):
    __tablename__ = "page_photos"
    __table_args__ = (
        UniqueConstraint("page_id", "photo_id", name="uq_page_photos_page_photo"),
        UniqueConstraint("page_id", "order_index", name="uq_page_photos_page_order"),
    )

    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), primary_key=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    order_index: Mapped[int] = mapped_column(nullable=False)
    slot_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    focal_x: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    focal_y: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)

    page = relationship("Page", back_populates="photo_links")
    photo = relationship("Photo", back_populates="page_links")
