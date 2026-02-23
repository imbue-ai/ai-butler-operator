import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import extension_api, test_ui, vapi_webhook, websocket_router
from app.services.session_manager import SessionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

session_manager = SessionManager()


async def _cleanup_loop():
    """Periodically clean up expired sessions."""
    while True:
        await asyncio.sleep(60)
        try:
            await session_manager.cleanup_expired()
        except Exception:
            logger.exception("Cleanup error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inject session_manager into routers
    extension_api.session_manager = session_manager
    websocket_router.session_manager = session_manager
    vapi_webhook.session_manager = session_manager
    test_ui.session_manager = session_manager

    cleanup_task = asyncio.create_task(_cleanup_loop())
    logger.info("PhoneBrowserUse server started")
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("PhoneBrowserUse server stopped")


app = FastAPI(title="PhoneBrowserUse", lifespan=lifespan)

# CORS
origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(extension_api.router)
app.include_router(websocket_router.router)
app.include_router(vapi_webhook.router)
app.include_router(test_ui.router)

# Static files & test UI
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/test")
async def serve_test_ui():
    return FileResponse(STATIC_DIR / "test.html")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "active_sessions": session_manager.active_count,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
