from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import get_db, get_summary_service
from app.models import SummaryRequest
from app.summarize.llm import RemoteSummaryRateLimited

router = APIRouter(prefix="/api/summaries", tags=["summaries"])


@router.get("")
def list_summaries(request: Request, limit: int = 20) -> list[dict]:
    return get_db(request).list_summaries(limit)


@router.post("")
async def generate_summary(payload: SummaryRequest, request: Request) -> dict:
    try:
        return await get_summary_service(request).generate_ad_hoc(payload.window_name, payload.repeater_id)
    except RemoteSummaryRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Summary provider returned HTTP {exc.response.status_code}.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Summary provider request failed: {exc}") from exc


@router.get("/queue")
def list_summary_queue(request: Request, limit: int = 200) -> list[dict]:
    return get_db(request).list_summary_jobs(limit)


@router.delete("/queue/{job_id}")
def delete_summary_queue_job(job_id: int, request: Request) -> dict[str, int | str]:
    db = get_db(request)
    if not db.query_one("SELECT id FROM summary_jobs WHERE id = ?", (job_id,)):
        raise HTTPException(status_code=404, detail="Summary queue job not found")
    db.delete_summary_job(job_id)
    return {"status": "deleted", "id": job_id}


@router.delete("/queue")
def clear_summary_queue(request: Request) -> dict[str, int | str]:
    deleted = get_db(request).clear_summary_jobs()
    return {"status": "cleared", "deleted": deleted}


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
