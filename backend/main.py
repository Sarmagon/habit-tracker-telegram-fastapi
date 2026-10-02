import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from backend.controllers.routes import router
from backend.database import SessionFactory
from backend.services.notifications import run_notification_worker
from common.config import Settings

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def manage_application_lifespan(application):
    settings = Settings().load_runtime_secrets()
    stop_event = threading.Event()
    worker_state = {"last_success": time.monotonic()}
    application.state.worker_state = worker_state
    notification_thread = threading.Thread(
        target=run_notification_worker,
        args=(settings, stop_event, worker_state),
        daemon=True,
    )
    notification_thread.start()
    application.state.notification_thread = notification_thread
    yield
    stop_event.set()
    notification_thread.join(timeout=15)


application = FastAPI(title="Habit Tracker", lifespan=manage_application_lifespan)
application.include_router(router, prefix="/api/v1")


@application.get("/health/live")
def check_liveness():
    return {"status": "ok"}


@application.get("/health/ready")
def check_readiness():
    worker_state = getattr(application.state, "worker_state", None)
    if worker_state and time.monotonic() - worker_state["last_success"] > 120:
        raise HTTPException(503, "Notification worker is stalled")
    try:
        with SessionFactory() as database_session:
            database_session.execute(text("SELECT 1 FROM users LIMIT 1"))
    except Exception as error:
        raise HTTPException(503, "Database unavailable") from error
    return {"status": "ready"}
