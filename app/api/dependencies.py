from __future__ import annotations

from pathlib import Path

from fastapi import Request

from app.config import AppConfig
from app.db import Database
from app.notify.webpush import KeywordEngine, NotificationService
from app.sdr.manager import ReceiverManager
from app.summarize.llm import SummaryService


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


def get_config_path(request: Request) -> Path:
    return request.app.state.config_path


def get_data_dir(request: Request) -> Path:
    return request.app.state.data_dir


def get_receiver_manager(request: Request) -> ReceiverManager:
    return request.app.state.receiver_manager


def get_notification_service(request: Request) -> NotificationService:
    return request.app.state.notification_service


def get_keyword_engine(request: Request) -> KeywordEngine:
    return request.app.state.keyword_engine


def get_summary_service(request: Request) -> SummaryService:
    return request.app.state.summary_service
