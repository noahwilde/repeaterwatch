from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.activity_chat import router as activity_chat_router
from app.api.callsigns import router as callsigns_router
from app.api.notifications import router as notifications_router
from app.api.live import router as live_router
from app.api.recordings import router as recordings_router
from app.api.repeaters import router as repeaters_router
from app.api.summaries import router as summaries_router
from app.api.system import router as system_router
from app.config import AppConfig, load_config
from app.db import Database
from app.notify.webpush import KeywordEngine, NotificationService, ReceiverHealthNotifier
from app.sdr.manager import ReceiverManager
from app.summarize.chat import ActivityChatService
from app.summarize.llm import SummaryService, SummaryWorker
from app.transcribe.whisper import TranscriptionWorker

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("REPEATERWATCH_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_app(config_path: str | Path | None = None) -> FastAPI:
    configure_logging()
    resolved_config_path = Path(
        config_path or os.getenv("REPEATERWATCH_CONFIG", "config.toml")
    ).expanduser().resolve()
    config = load_config(resolved_config_path)
    data_dir = config.storage.resolved_data_dir(resolved_config_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(data_dir / "repeaterwatch.sqlite3")
        db.seed_repeaters(config.repeaters)
        notification_service = NotificationService(db, config)
        receiver_health_notifier = ReceiverHealthNotifier(notification_service)
        keyword_engine = KeywordEngine(db, notification_service)
        receiver_manager = ReceiverManager(db, config, data_dir, receiver_health_notifier)
        summary_service = SummaryService(db, config)
        activity_chat_service = ActivityChatService(db, config)
        transcription_worker = TranscriptionWorker(db, config, keyword_engine)
        summary_worker = SummaryWorker(db, config, keyword_engine)

        app.state.config_path = resolved_config_path
        app.state.config = config
        app.state.data_dir = data_dir
        app.state.db = db
        app.state.notification_service = notification_service
        app.state.receiver_health_notifier = receiver_health_notifier
        app.state.keyword_engine = keyword_engine
        app.state.receiver_manager = receiver_manager
        app.state.summary_service = summary_service
        app.state.activity_chat_service = activity_chat_service
        app.state.transcription_worker = transcription_worker
        app.state.summary_worker = summary_worker

        await receiver_manager.sync()
        tasks = [
            asyncio.create_task(transcription_worker.run(), name="transcription-worker"),
            asyncio.create_task(summary_worker.run(), name="summary-worker"),
        ]
        app.state.background_tasks = tasks
        try:
            yield
        finally:
            transcription_worker.stop()
            summary_worker.stop()
            await receiver_manager.stop_all()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            db.close()

    app = FastAPI(title="RepeaterWatch", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(activity_chat_router)
    app.include_router(callsigns_router)
    app.include_router(system_router)
    app.include_router(live_router)
    app.include_router(repeaters_router)
    app.include_router(recordings_router)
    app.include_router(summaries_router)
    app.include_router(notifications_router)

    static_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
