import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import init_db
from app.services.events import start_consumers
from py_shared.errors import install_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    consumer_task = asyncio.create_task(start_consumers())
    yield
    consumer_task.cancel()


app = FastAPI(title="CreditFlow Notification Service", lifespan=lifespan)
install_error_handlers(app)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
