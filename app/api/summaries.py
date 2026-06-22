from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import get_db, get_summary_service
from app.models import SummaryRequest

router = APIRouter(prefix="/api/summaries", tags=["summaries"])


@router.get("")
def list_summaries(request: Request, limit: int = 20) -> list[dict]:
    return get_db(request).list_summaries(limit)


@router.post("")
async def generate_summary(payload: SummaryRequest, request: Request) -> dict:
    return await get_summary_service(request).generate_ad_hoc(payload.window_name, payload.repeater_id)


@router.delete("/{summary_id}")
def delete_summary(summary_id: int, request: Request) -> dict[str, int | str]:
    db = get_db(request)
    if not db.get_summary(summary_id):
        raise HTTPException(status_code=404, detail="Summary not found")
    db.delete_summary(summary_id)
    return {"status": "deleted", "id": summary_id}


@router.delete("")
def clear_summaries(request: Request) -> dict[str, int | str]:
    deleted = get_db(request).clear_summaries()
    return {"status": "cleared", "deleted": deleted}
