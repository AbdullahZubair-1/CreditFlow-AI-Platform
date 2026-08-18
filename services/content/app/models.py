import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Content(Base):
    __tablename__ = "content"
    # updated_at is server-generated (onupdate=func.now()) — without
    # eager_defaults, the async ORM marks it "expired" after an UPDATE and
    # only refetches it on next access via a plain synchronous attribute
    # read, which isn't awaitable and crashes with MissingGreenlet outside
    # of SQLAlchemy's own internal await chain. update_content() hits this
    # every time (snapshot a version, commit, then rebuild the response
    # from the same object) since it's the one write path that touches
    # content.updated_at right after commit. eager_defaults makes every
    # INSERT/UPDATE fetch server-generated columns back via RETURNING in
    # the same round trip, so there's nothing left to lazily reload.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    # draft | approved | published
    source_generation_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_scrape_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ContentVersion(Base):
    """Append-only snapshot taken on every edit — content.version points at
    the latest version_number here, but past snapshots are never mutated
    or deleted."""

    __tablename__ = "content_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ondelete="CASCADE" so deleting a Content row (see the DELETE
    # /content/{id} endpoint) doesn't fail with a foreign key violation
    # against its own version history — the versions are meaningless
    # without the content they snapshot, so they should go with it.
    content_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content.content.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    edited_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
