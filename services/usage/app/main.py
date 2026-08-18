import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.db import init_db
from app.events import start_consumers
from app.reconciliation import run_reconciliation_loop
from py_shared.errors import install_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    consumer_task = asyncio.create_task(start_consumers())
    reconciliation_task = asyncio.create_task(run_reconciliation_loop())
    yield
    consumer_task.cancel()
    reconciliation_task.cancel()


app = FastAPI(title="CreditFlow Usage/Metering Service", lifespan=lifespan)
install_error_handlers(app)
app.include_router(router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
