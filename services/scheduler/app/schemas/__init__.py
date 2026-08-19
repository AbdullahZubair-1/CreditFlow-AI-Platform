from datetime import datetime

from pydantic import BaseModel


class CreateScheduleRequest(BaseModel):
    content_id: str
    publish_at: datetime  # must be timezone-aware; stored/compared in UTC
    recurrence: str = "none"


class RescheduleRequest(BaseModel):
    publish_at: datetime | None = None
    recurrence: str | None = None


class ScheduledPostResponse(BaseModel):
    id: str
    account_id: str
    content_id: str
    publish_at: datetime
    status: str
    recurrence: str
    occurrences_fired: int
    created_at: datetime
