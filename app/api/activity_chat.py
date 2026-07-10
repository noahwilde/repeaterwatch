from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import get_activity_chat_service
from app.models import ActivityChatRequest
from app.provider_errors import provider_error_details, provider_error_is_insufficient_quota

router = APIRouter(prefix="/api/activity-chat", tags=["activity-chat"])


def _activity_chat_http_error(exc: httpx.HTTPStatusError) -> HTTPException:
    status_code = exc.response.status_code
    details = provider_error_details(exc.response)
    if status_code == 429:
        if provider_error_is_insufficient_quota(details):
            detail = (
                "Activity chat provider reported insufficient quota. "
                "Check OpenAI API credit, project budget, and billing settings."
            )
        else:
            detail = (
                "Activity chat provider returned 429 Too Many Requests. "
                "API quota or rate limits are currently blocking the request."
            )
        if details.message:
            detail = f"{detail} Provider message: {details.message}"
        return HTTPException(status_code=429, detail=detail)
    detail = f"Activity chat provider returned HTTP {status_code}."
    if details.message:
        detail = f"{detail} Provider message: {details.message}"
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
