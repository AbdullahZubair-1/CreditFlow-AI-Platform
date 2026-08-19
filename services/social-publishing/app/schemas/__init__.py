from datetime import datetime

from pydantic import BaseModel


class ConnectResponse(BaseModel):
    authorize_url: str


class ConnectionStatusResponse(BaseModel):
    connected: bool
    linkedin_member_urn: str | None = None
    expires_at: datetime | None = None


class PublishJobResponse(BaseModel):
    id: str
    scheduled_post_id: str
    content_id: str
    status: str
    linkedin_post_id: str | None
    error_reason: str | None
    created_at: datetime
    completed_at: datetime | None
