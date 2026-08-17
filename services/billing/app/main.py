import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.db import init_db
from app.dunning import run_dunning_scanner
from app.events import start_consumers
from app.outbox import run_outbox_poller
from py_shared.errors import install_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    consumer_task = asyncio.create_task(start_consumers())
    outbox_task = asyncio.create_task(run_outbox_poller())
    dunning_task = asyncio.create_task(run_dunning_scanner())
    yield
    consumer_task.cancel()
    outbox_task.cancel()
    dunning_task.cancel()


app = FastAPI(title="CreditFlow Billing Service", lifespan=lifespan)
install_error_handlers(app)
app.include_router(router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
