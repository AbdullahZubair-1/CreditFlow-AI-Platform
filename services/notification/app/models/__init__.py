import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The domain event that triggered this send. The outer processed_events
    # check (see py_shared.rabbitmq.consume's docstring) doesn't cover a
    # crash between email_client.send_email() actually succeeding and this
    # row's commit landing — on redelivery that window would otherwise
    # resend the same email. Checking for an existing "sent" row with this
    # source_event_id before sending closes that gap.
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # sent | failed
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
