from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import AppConfig
from app.db import Database


@dataclass
class CleanupReport:
    audio_deleted: int = 0
    transcripts_deleted: int = 0
    summaries_deleted: int = 0


def cleanup_retention(db: Database, config: AppConfig, now: datetime | None = None) -> CleanupReport:
    now = now or datetime.now(UTC)
    report = CleanupReport()
    audio_cutoff = now - timedelta(days=config.retention.raw_audio_days)
    transcript_cutoff = now - timedelta(days=config.retention.transcripts_days)
    summary_cutoff = now - timedelta(days=config.retention.summaries_days)

    for recording in db.query_all("SELECT * FROM recordings WHERE start_time < ?", (audio_cutoff.isoformat(timespec="seconds"),)):
        transcript = db.get_transcript_for_recording(int(recording["id"]))
        if not transcript and not config.retention.delete_metadata_without_summary:
            continue
        audio_path = Path(recording["audio_path"])
        if audio_path.exists():
            audio_path.unlink()
            report.audio_deleted += 1
        db.execute(
            "UPDATE recordings SET status = 'audio_deleted', audio_path = ? WHERE id = ?",
            (str(audio_path), recording["id"]),
        )

    for summary in db.query_all("SELECT * FROM summaries WHERE created_at < ?", (summary_cutoff.isoformat(timespec="seconds"),)):
        db.execute("DELETE FROM summaries WHERE id = ?", (summary["id"],))
        report.summaries_deleted += 1

    if config.retention.delete_metadata_without_summary:
        for transcript in db.query_all("SELECT * FROM transcripts WHERE created_at < ?", (transcript_cutoff.isoformat(timespec="seconds"),)):
            db.execute("DELETE FROM transcripts WHERE id = ?", (transcript["id"],))
            report.transcripts_deleted += 1

    return report
