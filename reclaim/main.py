"""RECLAIM — FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from reclaim.config import get_settings
from reclaim.dashboard.router import dashboard_ui_router
from reclaim.db.session import dispose_engine, init_engine
from reclaim.ingestion.router import router as ingestion_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan — initialize and teardown resources."""
    settings = get_settings()
    logger.info(f"Starting RECLAIM (env={settings.APP_ENV})")
    await init_engine()

    from reclaim.db.models import Base
    from reclaim.db.session import get_engine
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield
    await dispose_engine()
    logger.info("RECLAIM shut down")


app = FastAPI(
    title="RECLAIM",
    description="Autonomous Revenue Recovery Engine for Merchants",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Routes ---
app.include_router(ingestion_router)
app.include_router(dashboard_ui_router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "reclaim"}
