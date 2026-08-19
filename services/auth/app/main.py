from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.database import init_db
from py_shared.errors import install_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="CreditFlow Auth Service", lifespan=lifespan)
install_error_handlers(app)
app.include_router(router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
