import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends

from app import events, mongo
from app.config import RECURRENCE_INTERVALS_SECONDS
from app.identity import Identity, require_identity
from app.schemas import CreateScrapeJobRequest, ScrapedDocumentResponse, ScrapeJobResponse
from py_shared.errors import ApiError

router = APIRouter()


def _job_to_response(doc: dict) -> ScrapeJobResponse:
    return ScrapeJobResponse(
        id=doc["_id"],
        account_id=doc["account_id"],
        target_url=doc["target_url"],
        job_type=doc["job_type"],
        status=doc["status"],
        recurrence=doc["recurrence"],
        error_reason=doc.get("error_reason"),
        created_at=doc["created_at"],
        completed_at=doc.get("completed_at"),
    )


@router.post("/scrape-jobs", response_model=ScrapeJobResponse, status_code=202)
async def create_scrape_job(
    body: CreateScrapeJobRequest, identity: Identity = Depends(require_identity)
) -> ScrapeJobResponse:
    if body.recurrence not in RECURRENCE_INTERVALS_SECONDS:
        raise ApiError(
            "invalid_recurrence", f"recurrence must be one of {sorted(RECURRENCE_INTERVALS_SECONDS)}.", 400
        )

    job_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    interval = RECURRENCE_INTERVALS_SECONDS[body.recurrence]

    doc = {
        "_id": job_id,
        "account_id": identity.account_id,
        "target_url": body.target_url,
        "job_type": body.job_type,
        "status": "pending",
        "recurrence": body.recurrence,
        "next_run_at": (now + timedelta(seconds=interval)) if interval else None,
        "error_reason": None,
        "created_at": now,
        "completed_at": None,
    }
    await mongo.scrape_jobs().insert_one(doc)
    await events.publish_scrape_requested(job_id, identity.account_id, body.target_url, body.job_type)

    return _job_to_response(doc)


@router.get("/scrape-jobs", response_model=list[ScrapeJobResponse])
async def list_scrape_jobs(identity: Identity = Depends(require_identity)) -> list[ScrapeJobResponse]:
    cursor = mongo.scrape_jobs().find({"account_id": identity.account_id}).sort("created_at", -1)
    return [_job_to_response(doc) async for doc in cursor]


@router.get("/scrape-jobs/{job_id}", response_model=ScrapeJobResponse)
async def get_scrape_job(job_id: str, identity: Identity = Depends(require_identity)) -> ScrapeJobResponse:
    doc = await mongo.scrape_jobs().find_one({"_id": job_id, "account_id": identity.account_id})
    if not doc:
        raise ApiError("not_found", "Scrape job not found.", 404)
    return _job_to_response(doc)


@router.get("/scraped-documents/{document_id}", response_model=ScrapedDocumentResponse)
async def get_scraped_document(document_id: str, identity: Identity = Depends(require_identity)) -> ScrapedDocumentResponse:
    doc = await mongo.scraped_documents().find_one({"_id": document_id})
    if not doc:
        raise ApiError("not_found", "Scraped document not found.", 404)

    job = await mongo.scrape_jobs().find_one({"_id": doc["scrape_job_id"], "account_id": identity.account_id})
    if not job:
        raise ApiError("not_found", "Scraped document not found.", 404)

    return ScrapedDocumentResponse(
        id=doc["_id"],
        scrape_job_id=doc["scrape_job_id"],
        url=doc["url"],
        title=doc["title"],
        text_content=doc["text_content"],
        created_at=doc["created_at"],
    )
