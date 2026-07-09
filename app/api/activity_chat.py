from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import get_activity_chat_service
from app.models import ActivityChatRequest

router = APIRouter(prefix="/api/activity-chat", tags=["activity-chat"])


def _provider_error_text(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        return response.text.strip()
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message).strip()
        if payload.get("message"):
            return str(payload["message"]).strip()
    return ""


def _activity_chat_http_error(exc: httpx.HTTPStatusError) -> HTTPException:
    status_code = exc.response.status_code
    provider_text = _provider_error_text(exc.response)
    if status_code == 429:
        detail = (
            "Activity chat provider returned 429 Too Many Requests. "
            "API quota or rate limits are currently blocking the request."
        )
        if provider_text:
            detail = f"{detail} Provider message: {provider_text}"
        return HTTPException(status_code=429, detail=detail)
    detail = f"Activity chat provider returned HTTP {status_code}."
    if provider_text:
        detail = f"{detail} Provider message: {provider_text}"
    return HTTPException(status_code=502, detail=detail)


@router.post("")
async def activity_chat(payload: ActivityChatRequest, request: Request) -> dict:
    try:
        return await get_activity_chat_service(request).answer(payload)
    except httpx.HTTPStatusError as exc:
        raise _activity_chat_http_error(exc) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Activity chat provider request failed: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
