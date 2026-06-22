from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter, Query, Request

from app.api.dependencies import get_config, get_data_dir, get_db, get_receiver_manager
from app.config import AppConfig, public_config, save_config
from app.sdr.passband import passband_status

router = APIRouter(prefix="/api", tags=["system"])


def activity_bucket_minutes(activity_hours: int) -> int:
    if activity_hours <= 3:
        return 5
    if activity_hours <= 24:
        return 15
    if activity_hours <= 72:
        return 60
    return 120


def disk_usage(path) -> dict:
    path.mkdir(parents=True, exist_ok=True)
    total, used, free = shutil.disk_usage(path)
    return {"total": total, "used": used, "free": free}


@router.get("/dashboard")
def dashboard(
    request: Request,
    activity_hours: int = Query(default=24, ge=1, le=24 * 14),
) -> dict:
    config = get_config(request)
    data = get_db(request).dashboard(
        activity_hours=activity_hours,
        activity_bucket_minutes=activity_bucket_minutes(activity_hours),
        transcript_limit=config.retention.transcript_display_limit,
        summary_limit=config.retention.summary_display_limit,
    )
    data["disk_usage"] = disk_usage(get_data_dir(request))
    data["config"] = public_config(config)
    data["sdr_window"] = passband_status(data["repeaters"], config.sdr)
    return data


@router.get("/logs")
def logs(limit: int = Query(default=200, ge=20, le=1000)) -> dict:
    if shutil.which("journalctl") is None:
        return {
            "available": False,
            "lines": [],
            "error": "journalctl is unavailable on this host.",
        }

    command = [
        "journalctl",
        "-u",
        "repeaterwatch",
        "-n",
        str(limit),
        "--no-pager",
        "-o",
        "short-iso",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except subprocess.TimeoutExpired:
        return {"available": False, "lines": [], "error": "Timed out while reading service logs."}
    except OSError as exc:
        return {"available": False, "lines": [], "error": str(exc)}

    lines = result.stdout.splitlines()
    if result.returncode != 0:
        return {
            "available": False,
            "lines": lines[-limit:],
            "error": (result.stderr or "journalctl returned an error.").strip()[-800:],
        }
    return {"available": True, "lines": lines[-limit:], "error": ""}


@router.get("/config")
def config(request: Request) -> dict:
    return public_config(get_config(request))


@router.post("/receivers/restart")
async def restart_receivers(request: Request) -> dict:
    receiver_manager = get_receiver_manager(request)
    await receiver_manager.stop_all()
    await receiver_manager.sync()
    return {"status": "restarted", "receiver_status": get_db(request).list_receiver_status()}


@router.put("/config")
async def update_config(payload: dict, request: Request) -> dict:
    updated = AppConfig.model_validate(payload)
    save_config(updated, request.app.state.config_path)
    request.app.state.config = updated
    request.app.state.receiver_manager.config = updated
    request.app.state.notification_service.config = updated
    request.app.state.summary_service.config = updated
    request.app.state.transcription_worker.config = updated
    request.app.state.transcription_worker.service.config = updated
    request.app.state.summary_worker.config = updated
    request.app.state.summary_worker.service.config = updated
    await request.app.state.receiver_manager.sync()
    return public_config(updated)


@router.put("/audio-settings")
async def update_audio_settings(payload: dict, request: Request) -> dict:
    current = get_config(request)
    data = current.model_dump(mode="json")
    if "vox" in payload:
        data["vox"] = {**data["vox"], **payload["vox"]}
    if "retention" in payload:
        data["retention"] = {**data["retention"], **payload["retention"]}
    if "transcription" in payload:
        data["transcription"] = {**data["transcription"], **payload["transcription"]}
    if "summary" in payload:
        data["summary"] = {**data["summary"], **payload["summary"]}
    updated = AppConfig.model_validate(data)
    save_config(updated, request.app.state.config_path)
    request.app.state.config = updated
    request.app.state.receiver_manager.config = updated
    request.app.state.notification_service.config = updated
    request.app.state.summary_service.config = updated
    request.app.state.transcription_worker.config = updated
    request.app.state.transcription_worker.service.config = updated
    request.app.state.summary_worker.config = updated
    request.app.state.summary_worker.service.config = updated
    if updated.vox != current.vox:
        await request.app.state.receiver_manager.stop_all()
        await request.app.state.receiver_manager.sync()
    return public_config(updated)
