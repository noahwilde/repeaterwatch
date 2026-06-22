from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config import AppConfig
from app.db import Database
from app.retention import cleanup_retention


def test_cleanup_deletes_old_audio_only_after_transcript(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        config = AppConfig()
        now = datetime(2026, 2, 1, tzinfo=UTC)
        old = now - timedelta(days=40)
        audio_path = tmp_path / "old.wav"
        audio_path.write_bytes(b"audio")
        recording_id = db.add_recording(
            {
                "frequency_mhz": 146.94,
                "repeater_name": "Local",
                "start_time": old.isoformat(timespec="seconds"),
                "end_time": old.isoformat(timespec="seconds"),
                "duration_seconds": 2.0,
                "audio_path": str(audio_path),
                "status": "completed",
            }
        )

        report = cleanup_retention(db, config, now=now)
        assert report.audio_deleted == 0
        assert audio_path.exists()

        db.add_transcript(
            recording_id,
            text="test",
            original_text="test",
            confidence=0.9,
            low_confidence=False,
            backend="noop",
            segments=[],
        )
        report = cleanup_retention(db, config, now=now)
        assert report.audio_deleted == 1
        assert not audio_path.exists()
        assert db.get_recording(recording_id)["status"] == "audio_deleted"
    finally:
        db.close()
