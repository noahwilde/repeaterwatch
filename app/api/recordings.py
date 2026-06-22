from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.dependencies import get_db
from app.models import TranscriptCorrectionIn

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


def _delete_audio_file(recording: dict) -> bool:
    path = Path(recording["audio_path"])
    if not path.exists():
        return False
    path.unlink()
    return True


def _clear_recording_rows(db, recordings: list[dict]) -> dict[str, int | str]:
    audio_deleted = 0
    seen_paths: set[str] = set()
    for recording in recordings:
        audio_path = str(recording["audio_path"])
        if audio_path in seen_paths:
            continue
        seen_paths.add(audio_path)
        if _delete_audio_file(recording):
            audio_deleted += 1
    deleted = 0
    for recording in recordings:
        db.delete_recording(int(recording["id"]))
        deleted += 1
    return {"status": "cleared", "deleted": deleted, "audio_deleted": audio_deleted}


@router.get("")
def list_recordings(request: Request, limit: int = 50) -> list[dict]:
    return get_db(request).list_recordings(limit)


@router.get("/{recording_id}")
def get_recording(recording_id: int, request: Request) -> dict:
    recording = get_db(request).get_recording(recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    transcript = get_db(request).get_transcript_for_recording(recording_id)
    return {"recording": recording, "transcript": transcript}


@router.get("/{recording_id}/audio")
def get_audio(recording_id: int, request: Request) -> FileResponse:
    recording = get_db(request).get_recording(recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    path = Path(recording["audio_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file no longer exists")
    return FileResponse(path, media_type="audio/wav", filename=path.name, content_disposition_type="inline")


@router.put("/{recording_id}/transcript")
def correct_transcript(recording_id: int, payload: TranscriptCorrectionIn, request: Request) -> dict:
    db = get_db(request)
    transcript = db.get_transcript_for_recording(recording_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    db.update_transcript_correction(int(transcript["id"]), payload.corrected_text)
    return db.get_transcript_for_recording(recording_id) or {}


@router.delete("/static-only")
def clear_static_only_recordings(request: Request) -> dict[str, int | str]:
    db = get_db(request)
    return _clear_recording_rows(db, db.list_static_only_recordings())


@router.delete("/{recording_id}")
def delete_recording(recording_id: int, request: Request) -> dict[str, int | str | bool]:
    db = get_db(request)
    recording = db.get_recording(recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    audio_deleted = _delete_audio_file(recording)
    db.delete_recording(recording_id)
    return {"status": "deleted", "id": recording_id, "audio_deleted": audio_deleted}


@router.delete("")
def clear_recordings(request: Request) -> dict[str, int | str]:
    db = get_db(request)
    return _clear_recording_rows(db, db.query_all("SELECT * FROM recordings"))
