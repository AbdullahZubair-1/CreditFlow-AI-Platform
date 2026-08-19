import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.database import init_indexes
from app.services.events import start_consumer
from app.services.recurring import run_recurring_loop
from py_shared.errors import install_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_indexes()
    consumer_task = asyncio.create_task(start_consumer())
    recurring_task = asyncio.create_task(run_recurring_loop())
    yield
    consumer_task.cancel()
    recurring_task.cancel()


app = FastAPI(title="CreditFlow Scraper Service", lifespan=lifespan)
install_error_handlers(app)
app.include_router(router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
