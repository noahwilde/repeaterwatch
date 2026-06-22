from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api.system import api_usage_bucket_minutes
from app.db import Database


def test_api_usage_report_groups_call_types_and_totals(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
        db.add_api_usage_event(
            {
                "created_at": (now - timedelta(hours=2)).isoformat(timespec="seconds"),
                "provider": "openai-compatible",
                "call_type": "transcription",
                "operation": "recording",
                "model": "gpt-4o-transcribe",
                "status": "success",
                "source_type": "recording",
                "source_id": 10,
                "input_count": 1,
                "audio_duration_seconds": 12.5,
                "elapsed_ms": 900,
                "reason": "remote_transcription",
            }
        )
        db.add_api_usage_event(
            {
                "created_at": (now - timedelta(hours=1)).isoformat(timespec="seconds"),
                "provider": "openai-compatible",
                "call_type": "summary",
                "operation": "scheduled",
                "model": "gpt-4.1-mini",
                "status": "success",
                "window_name": "hour",
                "input_count": 3,
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
                "elapsed_ms": 700,
                "reason": "remote_summary",
            }
        )
        db.add_api_usage_event(
            {
                "created_at": (now - timedelta(minutes=30)).isoformat(timespec="seconds"),
                "provider": "openai-compatible",
                "call_type": "summary",
                "operation": "scheduled",
                "model": "gpt-4.1-mini",
                "status": "skipped",
                "window_name": "quarter_hour",
                "input_count": 1,
                "reason": "automated_only",
            }
        )

        report = db.api_usage_report(now=now, hours=6, bucket_minutes=60)
        summary = next(row for row in report["call_types"] if row["call_type"] == "summary")
        transcription = next(row for row in report["call_types"] if row["call_type"] == "transcription")

        assert report["totals"]["events"] == 3
        assert report["totals"]["remote_calls"] == 2
        assert report["totals"]["skipped"] == 1
        assert report["totals"]["audio_duration_seconds"] == 12.5
        assert report["totals"]["total_tokens"] == 150
        assert summary["remote_calls"] == 1
        assert summary["skipped"] == 1
        assert summary["total_tokens"] == 150
        assert transcription["remote_calls"] == 1
        assert transcription["audio_duration_seconds"] == 12.5
        assert report["models"][0]["model"] == "gpt-4.1-mini"
        assert any(reason["reason"] == "automated_only" for reason in report["reasons"])
        assert len(report["recent_events"]) == 3
    finally:
        db.close()


def test_api_usage_bucket_minutes_keeps_ranges_readable():
    assert api_usage_bucket_minutes(6) == 15
    assert api_usage_bucket_minutes(24) == 60
    assert api_usage_bucket_minutes(72) == 180
    assert api_usage_bucket_minutes(720) == 720
