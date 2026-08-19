import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.database import init_db
from app.services.events import start_consumer
from app.services.token_refresh import run_token_refresh_loop
from py_shared.errors import install_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    consumer_task = asyncio.create_task(start_consumer())
    refresh_task = asyncio.create_task(run_token_refresh_loop())
    yield
    consumer_task.cancel()
    refresh_task.cancel()


app = FastAPI(title="CreditFlow Social Publishing Service", lifespan=lifespan)
install_error_handlers(app)
app.include_router(router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
