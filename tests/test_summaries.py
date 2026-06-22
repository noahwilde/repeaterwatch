from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone

from app.config import AppConfig
from app.db import Database
from app.summarize.llm import (
    SummaryService,
    SummaryWorker,
    build_summary_prompt,
    daily_activity_index,
    remove_absent_category_claims,
    scheduled_window_bounds,
    select_source_transcripts,
    window_bounds,
)


def _recording_with_transcript(db: Database, repeater_id: int, start_time: datetime, text: str) -> int:
    recording_id = db.add_recording(
        {
            "repeater_id": repeater_id,
            "frequency_mhz": 146.94,
            "repeater_name": f"Repeater {repeater_id}",
            "start_time": start_time.isoformat(timespec="seconds"),
            "end_time": start_time.isoformat(timespec="seconds"),
            "duration_seconds": 2.0,
            "audio_path": f"/tmp/{repeater_id}.wav",
            "status": "completed",
        }
    )
    return db.add_transcript(
        recording_id,
        text=text,
        original_text=text,
        confidence=0.9,
        low_confidence=False,
        backend="noop",
        segments=[],
    )


def test_summary_source_selection_window_and_repeater_filter(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_a = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745, "tone": "123.0"})
        repeater_b = db.create_repeater({"name": "B", "frequency_mhz": 147.0})
        now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        recent_a = _recording_with_transcript(db, repeater_a, now - timedelta(minutes=5), "recent a")
        _recording_with_transcript(db, repeater_a, now - timedelta(minutes=45), "old a")
        _recording_with_transcript(db, repeater_b, now - timedelta(minutes=4), "recent b")

        selection = select_source_transcripts(db, "last_15_minutes", repeater_id=repeater_a, now=now)

        assert [row["id"] for row in selection.transcripts] == [recent_a]
        assert selection.window_name == "quarter_hour"
        assert selection.transcripts[0]["configured_repeater_name"] == "K0RPT Main"
        assert selection.transcripts[0]["repeater_tone"] == "123.0"

        prompt = build_summary_prompt(selection)
        assert "K0RPT Main" in prompt
        assert "146.94 MHz" in prompt
        assert "Tone: 123.0" in prompt
        assert "trusted receiver context" in prompt
        assert "Transcript Class: possible user traffic" in prompt
        assert "Do not list absent categories" in prompt
        assert "Do not attribute automated repeater" in prompt
    finally:
        db.close()


def test_summary_prompt_labels_automated_only_transcripts(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745, "tone": "192.8"})
        now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        _recording_with_transcript(
            db,
            repeater_id,
            now - timedelta(minutes=1),
            "K0RPT repeater Example City. Use tone 192.8.",
        )

        selection = select_source_transcripts(db, "last_15_minutes", repeater_id=repeater_id, now=now)
        prompt = build_summary_prompt(selection)

        assert "Transcript Class: automated/system message only" in prompt
        assert "K0RPT repeater Example City. Use tone 192.8." in prompt
    finally:
        db.close()


def test_today_summary_window_uses_local_midnight(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745, "tone": "192.8"})
        central = timezone(timedelta(hours=-5), "CDT")
        now = datetime(2026, 6, 21, 1, 0, tzinfo=UTC)

        start, end = window_bounds("today", now=now, local_tz=central)

        assert start == datetime(2026, 6, 20, 5, 0, tzinfo=UTC)
        assert end == now

        _recording_with_transcript(
            db,
            repeater_id,
            datetime(2026, 6, 20, 4, 30, tzinfo=UTC),
            "previous local day",
        )
        _recording_with_transcript(
            db,
            repeater_id,
            datetime(2026, 6, 20, 23, 30, tzinfo=UTC),
            "same local evening",
        )

        selection = select_source_transcripts(db, "today", repeater_id=repeater_id, now=now, local_tz=central)
        prompt = build_summary_prompt(selection)

        assert [row["text"] for row in selection.transcripts] == ["same local evening"]
        assert "Window: day (2026-06-20 CDT" in prompt
        assert "18:30:00 CDT" in prompt
    finally:
        db.close()


def test_scheduled_summary_windows_align_to_local_boundaries():
    central = timezone(timedelta(hours=-5), "CDT")
    now = datetime(2026, 6, 21, 21, 44, 30, tzinfo=central)

    quarter_start, quarter_end = scheduled_window_bounds("quarter_hour", now=now, local_tz=central)
    hour_start, hour_end = scheduled_window_bounds("hour", now=now, local_tz=central)
    day_start, day_end = scheduled_window_bounds("day", now=now, local_tz=central)

    assert quarter_start.astimezone(central).replace(tzinfo=None) == datetime(2026, 6, 21, 21, 15)
    assert quarter_end.astimezone(central).replace(tzinfo=None) == datetime(2026, 6, 21, 21, 30)
    assert hour_start.astimezone(central).replace(tzinfo=None) == datetime(2026, 6, 21, 20, 0)
    assert hour_end.astimezone(central).replace(tzinfo=None) == datetime(2026, 6, 21, 21, 0)
    assert day_start.astimezone(central).replace(tzinfo=None) == datetime(2026, 6, 20, 0, 0)
    assert day_end.astimezone(central).replace(tzinfo=None) == datetime(2026, 6, 21, 0, 0)


def test_summary_worker_generates_scheduled_period_once(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745, "tone": "192.8"})
        now = datetime(2026, 6, 21, 21, 49, tzinfo=UTC)
        _recording_with_transcript(
            db,
            repeater_id,
            datetime(2026, 6, 21, 20, 30, tzinfo=UTC),
            "K0XYZ handled an hourly net check-in.",
        )
        _recording_with_transcript(
            db,
            repeater_id,
            datetime(2026, 6, 21, 21, 35, tzinfo=UTC),
            "K0ABC checked into the net.",
        )
        config = AppConfig()
        config.summary.backend = "noop"
        config.summary.timezone = "UTC"
        config.summary.scheduled_windows = ["quarter_hour", "hour"]
        config.summary.per_repeater_scheduled = True
        worker = SummaryWorker(db, config)

        first = asyncio.run(worker.generate_rolling(now=now))
        second = asyncio.run(worker.generate_rolling(now=now))
        summaries = db.list_summaries(20)

        assert len(first) == 4
        assert second == []
        assert sorted(summary["window_name"] for summary in summaries) == ["hour", "hour", "quarter_hour", "quarter_hour"]
        assert all(summary["start_time"].endswith("+00:00") for summary in summaries)
    finally:
        db.close()


def test_summary_worker_defaults_to_hourly_and_daily_without_per_repeater_duplicates(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745, "tone": "192.8"})
        now = datetime(2026, 6, 21, 21, 46, tzinfo=UTC)
        _recording_with_transcript(
            db,
            repeater_id,
            datetime(2026, 6, 21, 20, 30, tzinfo=UTC),
            "K0XYZ handled an hourly net check-in.",
        )
        _recording_with_transcript(
            db,
            repeater_id,
            datetime(2026, 6, 21, 21, 35, tzinfo=UTC),
            "K0ABC checked into the current quarter hour.",
        )
        config = AppConfig()
        config.summary.backend = "noop"
        config.summary.timezone = "UTC"
        worker = SummaryWorker(db, config)

        summary_ids = asyncio.run(worker.generate_rolling(now=now))
        summaries = db.list_summaries(20)

        assert len(summary_ids) == 1
        assert [(summary["window_name"], summary["repeater_id"]) for summary in summaries] == [("hour", None)]
    finally:
        db.close()


def test_summary_worker_can_disable_all_scheduled_windows(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745, "tone": "192.8"})
        now = datetime(2026, 6, 21, 21, 46, tzinfo=UTC)
        _recording_with_transcript(
            db,
            repeater_id,
            datetime(2026, 6, 21, 20, 30, tzinfo=UTC),
            "K0XYZ handled an hourly net check-in.",
        )
        config = AppConfig()
        config.summary.backend = "noop"
        config.summary.timezone = "UTC"
        config.summary.scheduled_windows = []
        worker = SummaryWorker(db, config)

        summary_ids = asyncio.run(worker.generate_rolling(now=now))

        assert summary_ids == []
        assert db.list_summaries(20) == []
    finally:
        db.close()


def test_automated_only_summary_skips_remote_model(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745, "tone": "192.8"})
        now = datetime(2026, 6, 21, 21, 46, tzinfo=UTC)
        _recording_with_transcript(
            db,
            repeater_id,
            datetime(2026, 6, 21, 21, 35, tzinfo=UTC),
            "K0RPT repeater Example City. Use tone 192.8.",
        )
        config = AppConfig()
        config.summary.backend = "openai-compatible"
        config.summary.timezone = "UTC"
        selection = select_source_transcripts(db, "last_15_minutes", repeater_id=repeater_id, now=now)
        service = SummaryService(db, config)

        summary_id = asyncio.run(service.generate_from_selection(selection, repeater_id))
        summary = db.get_summary(summary_id)
        usage_events = db.list_api_usage_events()

        assert summary["status"] == "automated_only"
        assert "automated/system repeater messages" in summary["text"]
        assert usage_events[0]["call_type"] == "summary"
        assert usage_events[0]["status"] == "skipped"
        assert usage_events[0]["reason"] == "automated_only"
    finally:
        db.close()


def test_daily_summary_prompt_includes_full_day_coverage_index(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745, "tone": "192.8"})
        now = datetime(2026, 3, 1, 22, 0, tzinfo=UTC)
        _recording_with_transcript(db, repeater_id, now.replace(hour=8, minute=0), "Morning commute check-in from K0ABC.")
        _recording_with_transcript(db, repeater_id, now.replace(hour=18, minute=0), "The evening net opened with net control K0NET.")
        _recording_with_transcript(db, repeater_id, now.replace(hour=18, minute=3), "The technical net followed with K0XYZ taking check-ins.")

        selection = select_source_transcripts(db, "today", repeater_id=repeater_id, now=now)
        index = daily_activity_index(selection)
        prompt = build_summary_prompt(selection)

        assert "Daily Activity Index" in index
        assert "Activity period 1" in index
        assert "Activity period 2" in index
        assert "Morning commute check-in" in index
        assert "evening net opened" in index
        assert "technical net followed" in index
        assert "Ensure complete chronological coverage of the entire day" in prompt
        assert "If multiple nets or check-in sessions occur back to back, mention each one separately" in prompt
    finally:
        db.close()


def test_summary_absent_category_cleanup_removes_notification_keywords():
    text = (
        "[K0RPT Main 146.745 MHz tone 192.8] Automated repeater IDs were heard; "
        "no weather, emergencies, nets, or user traffic present. Transcript quality uncertain."
    )

    cleaned = remove_absent_category_claims(text)

    assert "Automated repeater IDs were heard" in cleaned
    assert "Transcript quality uncertain" in cleaned
    assert "weather" not in cleaned.lower()
    assert "nets" not in cleaned.lower()
    assert "user traffic" not in cleaned.lower()
