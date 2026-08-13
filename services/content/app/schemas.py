from datetime import datetime

from pydantic import BaseModel


class CreateContentRequest(BaseModel):
    title: str
    body: str = ""
    image_url: str | None = None


class UpdateContentRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    image_url: str | None = None


class UpdateStatusRequest(BaseModel):
    status: str


class ContentResponse(BaseModel):
    id: str
    account_id: str
    created_by_user_id: str
    title: str
    body: str
    image_url: str | None
    status: str
    source_generation_job_id: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class ContentVersionResponse(BaseModel):
    version_number: int
    title: str
    body: str
    image_url: str | None
    edited_by_user_id: str
    created_at: datetime


class UploadImageResponse(BaseModel):
    image_url: str
