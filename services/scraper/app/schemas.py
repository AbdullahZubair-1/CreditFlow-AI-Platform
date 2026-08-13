from datetime import datetime

from pydantic import BaseModel


class CreateScrapeJobRequest(BaseModel):
    target_url: str
    job_type: str = "generic"
    recurrence: str = "none"  # none | daily | weekly


class ScrapeJobResponse(BaseModel):
    id: str
    account_id: str
    target_url: str
    job_type: str
    status: str
    recurrence: str
    error_reason: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ScrapedDocumentResponse(BaseModel):
    id: str
    scrape_job_id: str
    url: str
    title: str
    text_content: str
    created_at: datetime
