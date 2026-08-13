import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings
from app.db import init_db
from app.events import start_consumer
from py_shared.errors import install_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    consumer_task = asyncio.create_task(start_consumer())
    yield
    consumer_task.cancel()


app = FastAPI(title="CreditFlow Content Service", lifespan=lifespan)
install_error_handlers(app)
app.include_router(router)

os.makedirs(settings.upload_dir, exist_ok=True)
app.mount(settings.upload_base_url, StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
