from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.dependencies import get_activity_chat_service
from app.models import ActivityChatRequest

router = APIRouter(prefix="/api/activity-chat", tags=["activity-chat"])


@router.post("")
async def activity_chat(payload: ActivityChatRequest, request: Request) -> dict:
    return await get_activity_chat_service(request).answer(payload)
