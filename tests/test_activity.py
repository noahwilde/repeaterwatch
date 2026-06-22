from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api.system import activity_bucket_minutes
from app.db import Database


def test_recording_activity_groups_recordings_into_time_buckets(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745})
        other_repeater_id = db.create_repeater({"name": "Quiet", "frequency_mhz": 147.0})
        now = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)

        db.add_recording(
            {
                "repeater_id": repeater_id,
                "frequency_mhz": 146.745,
                "repeater_name": "K0RPT Main",
                "start_time": (now - timedelta(minutes=5)).isoformat(timespec="seconds"),
                "duration_seconds": 12.5,
                "audio_path": "/tmp/recent.wav",
                "status": "completed",
            }
        )
        db.add_recording(
            {
                "repeater_id": repeater_id,
                "frequency_mhz": 146.745,
                "repeater_name": "K0RPT Main",
                "start_time": (now - timedelta(minutes=20)).isoformat(timespec="seconds"),
                "duration_seconds": 3.0,
                "audio_path": "/tmp/older.wav",
                "status": "completed",
            }
        )
        db.add_recording(
            {
                "repeater_id": repeater_id,
                "frequency_mhz": 146.745,
                "repeater_name": "K0RPT Main",
                "start_time": (now - timedelta(hours=2)).isoformat(timespec="seconds"),
                "duration_seconds": 99.0,
                "audio_path": "/tmp/outside-window.wav",
                "status": "completed",
            }
        )

        activity = db.recording_activity(now=now, hours=1, bucket_minutes=15)
        active = next(row for row in activity["repeaters"] if row["repeater_id"] == repeater_id)
        quiet = next(row for row in activity["repeaters"] if row["repeater_id"] == other_repeater_id)

        assert activity["bucket_minutes"] == 15
        assert len(activity["buckets"]) == 4
        assert active["total_count"] == 2
        assert active["total_duration_seconds"] == 15.5
        assert [bucket["count"] for bucket in active["buckets"]] == [0, 0, 1, 1]
        assert [bucket["duration_seconds"] for bucket in active["buckets"]] == [0.0, 0.0, 3.0, 12.5]
        assert quiet["total_count"] == 0
    finally:
        db.close()


def test_dashboard_activity_window_is_configurable(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        activity = db.dashboard(activity_hours=6, activity_bucket_minutes=15)["activity"]

        assert activity["bucket_minutes"] == 15
        assert len(activity["buckets"]) == 24
    finally:
        db.close()


def test_dashboard_transcript_limit_controls_displayed_history(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        base_time = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
        for index in range(25):
            recording_id = db.add_recording(
                {
                    "frequency_mhz": 146.745,
                    "repeater_name": "K0RPT Main",
                    "start_time": (base_time - timedelta(minutes=index)).isoformat(timespec="seconds"),
                    "duration_seconds": 3.0,
                    "audio_path": f"/tmp/{index}.wav",
                    "status": "completed",
                }
            )
            db.add_transcript(
                recording_id,
                text=f"transcript {index}",
                original_text=f"transcript {index}",
                confidence=0.9,
                low_confidence=False,
                backend="noop",
                segments=[],
            )

        dashboard = db.dashboard(transcript_limit=25)

        assert len(dashboard["recordings"]) == 25
        assert len(dashboard["transcripts"]) == 25
    finally:
        db.close()


def test_activity_bucket_minutes_keeps_common_ranges_readable():
    assert activity_bucket_minutes(1) == 5
    assert activity_bucket_minutes(24) == 15
    assert activity_bucket_minutes(72) == 60
    assert activity_bucket_minutes(168) == 120
