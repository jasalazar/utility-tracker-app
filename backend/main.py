"""
FastAPI application entry point.

Responsibilities:
  - Mount the compiled React SPA under /
  - Register all API routers under /api and /auth
  - Register the Gmail webhook endpoint at /webhook/gmail
  - Expose a WebSocket endpoint at /ws/{uid}
  - Start / stop APScheduler on lifespan events
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.auth.middleware import get_current_uid
from backend.notifications.websocket import connect, disconnect
from backend.routers import auth, payments, rules, admin
from backend.webhook.gmail import router as gmail_router
from backend.scheduler.jobs import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.config import settings
    logger.info("Starting APScheduler…")
    start_scheduler()

    # Print the Pub/Sub webhook path so the operator can verify the push
    # subscription endpoint is correct.  When running locally you must
    # prepend your current ngrok URL (https://<id>.ngrok-free.app).
    webhook_path = f"/webhook/gmail?token={settings.pubsub_webhook_token}"
    logger.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    logger.info(
        "  Pub/Sub subscription endpoint — set this in Google Cloud Console:"
    )
    logger.info("  https://<your-ngrok-id>.ngrok-free.app%s", webhook_path)
    logger.info(
        "  Gmail watch status:  GET  http://localhost:8000/auth/watch-status"
    )
    logger.info(
        "  Re-register watch:   POST http://localhost:8000/auth/rewatch"
    )
    logger.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    yield
    logger.info("Stopping APScheduler…")
    stop_scheduler()


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Utility Tracker",
    description="Agentic household utility payment tracker",
    version="0.1.0",
    lifespan=lifespan,
    # Disable the default /docs in favour of keeping the SPA at /
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS — tighten origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API routers
# ---------------------------------------------------------------------------

app.include_router(auth.router)
app.include_router(payments.router)
app.include_router(rules.router)
app.include_router(admin.router)
app.include_router(gmail_router)


# ---------------------------------------------------------------------------
# WebSocket — real-time UI notifications
# ---------------------------------------------------------------------------

@app.websocket("/ws/{uid}")
async def websocket_endpoint(ws: WebSocket, uid: str) -> None:
    """
    Persistent WebSocket connection for a logged-in user.
    The frontend connects here to receive real-time payment and notification events.
    """
    await connect(uid, ws)
    try:
        while True:
            # Keep the connection alive; we only send server → client messages.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await disconnect(uid, ws)


# ---------------------------------------------------------------------------
# Serve the React SPA
# ---------------------------------------------------------------------------

if FRONTEND_DIST.exists():
    # Serve static assets (JS, CSS, images).
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        """
        Return index.html for every non-API route so React Router can handle
        client-side navigation (e.g. /dashboard, /settings).
        """
        return FileResponse(str(FRONTEND_DIST / "index.html"))
else:
    logger.warning(
        "Frontend dist not found at %s — run 'npm run build' inside frontend/",
        FRONTEND_DIST,
    )

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"message": "Utility Tracker API is running. Build the frontend to see the UI."}
