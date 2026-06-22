from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import get_config, get_config_path, get_db, get_receiver_manager
from app.config import AppConfig, RepeaterConfig, save_config
from app.models import RepeaterIn
from app.sdr.passband import passband_status

router = APIRouter(prefix="/api/repeaters", tags=["repeaters"])


def _apply_runtime_config(request: Request, config: AppConfig) -> None:
    request.app.state.config = config
    request.app.state.receiver_manager.config = config
    request.app.state.notification_service.config = config
    request.app.state.summary_service.config = config
    request.app.state.transcription_worker.config = config
    request.app.state.transcription_worker.service.config = config
    request.app.state.summary_worker.config = config
    request.app.state.summary_worker.service.config = config


def _persist_repeaters(request: Request) -> None:
    db = get_db(request)
    config = get_config(request)
    repeaters = [
        RepeaterConfig.model_validate({field: row.get(field) for field in RepeaterConfig.model_fields})
        for row in db.list_repeaters()
    ]
    updated = AppConfig.model_validate({**config.model_dump(mode="json"), "repeaters": [r.model_dump() for r in repeaters]})
    save_config(updated, get_config_path(request))
    _apply_runtime_config(request, updated)


def _validate_passband(request: Request, candidate_repeaters: list[dict]) -> None:
    config = get_config(request)
    enabled_count = sum(1 for row in candidate_repeaters if row.get("enabled"))
    if enabled_count <= 1 or not config.sdr.multi_repeater_enabled:
        return
    status = passband_status(candidate_repeaters, config.sdr)
    if status["can_monitor"]:
        return
    warnings = "; ".join(status.get("warnings") or [])
    detail = (
        "Enabled repeaters do not fit inside the current SDR passband. "
        f"Suggested center {status['recommended_center_frequency_mhz']:.6f} MHz; "
        f"required sample rate about {status['required_sample_rate_hz']:,} Hz. "
        f"{warnings}"
    ).strip()
    raise HTTPException(status_code=400, detail=detail)


@router.get("")
def list_repeaters(request: Request) -> list[dict]:
    return get_db(request).list_repeaters()


@router.post("")
async def create_repeater(payload: RepeaterIn, request: Request) -> dict:
    repeater = RepeaterConfig.model_validate(payload.model_dump())
    db = get_db(request)
    _validate_passband(request, db.list_repeaters() + [repeater.model_dump() | {"id": None}])
    try:
        repeater_id = db.create_repeater(repeater.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _persist_repeaters(request)
    await get_receiver_manager(request).sync()
    return db.get_repeater(repeater_id) or {}


@router.put("/{repeater_id}")
async def update_repeater(repeater_id: int, payload: RepeaterIn, request: Request) -> dict:
    repeater = RepeaterConfig.model_validate(payload.model_dump())
    db = get_db(request)
    if not db.get_repeater(repeater_id):
        raise HTTPException(status_code=404, detail="Repeater not found")
    candidate_repeaters = [
        (repeater.model_dump() | {"id": repeater_id}) if int(row["id"]) == int(repeater_id) else row
        for row in db.list_repeaters()
    ]
    _validate_passband(request, candidate_repeaters)
    try:
        db.update_repeater(repeater_id, repeater.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _persist_repeaters(request)
    receiver_manager = get_receiver_manager(request)
    await receiver_manager.stop_repeater(repeater_id)
    await receiver_manager.sync()
    return db.get_repeater(repeater_id) or {}


@router.delete("/{repeater_id}")
async def delete_repeater(repeater_id: int, request: Request) -> dict[str, str]:
    db = get_db(request)
    if not db.get_repeater(repeater_id):
        raise HTTPException(status_code=404, detail="Repeater not found")
    await get_receiver_manager(request).stop_repeater(repeater_id)
    db.delete_repeater(repeater_id)
    _persist_repeaters(request)
    await get_receiver_manager(request).sync()
    return {"status": "deleted"}
