from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import AppConfig
from app.db import Database
from app.notify.webpush import (
    KeywordEngine,
    NotificationService,
    non_automated_transcript_text,
    rule_matches_text,
    suppressed_by_phrase,
    transcript_excerpt,
)


def test_phrase_keyword_matches_case_insensitive():
    rule = {"keyword": "Weather", "is_regex": False, "case_sensitive": False}
    assert rule_matches_text(rule, "net control mentioned weather") == "Weather"


def test_regex_keyword_matches():
    rule = {"keyword": r"\bK[A-Z0-9]{2,5}\b", "is_regex": True, "case_sensitive": False}
    assert rule_matches_text(rule, "heard k9abc checking in") == "k9abc"


def test_keyword_rule_defaults_to_transcript_alerts(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        rule_id = db.create_keyword_rule({"keyword": "weather"})
        rule = next(row for row in db.list_keyword_rules() if row["id"] == rule_id)

        assert rule["notify_transcript"] is True
        assert rule["notify_summary"] is False
    finally:
        db.close()


def test_traffic_alert_setting_defaults_off(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        assert db.traffic_alerts_enabled() is False

        db.set_traffic_alerts_enabled(True)
        assert db.traffic_alerts_enabled() is True

        db.set_traffic_alerts_enabled(False)
        assert db.traffic_alerts_enabled() is False

        db.set_traffic_alert_suppress_phrases(" K0RPT repeater Example City \n\nUse tone 192.8\n")
        assert db.traffic_alert_suppress_phrases_text() == "K0RPT repeater Example City\nUse tone 192.8"
        assert db.traffic_alert_suppress_phrases() == ["K0RPT repeater Example City", "Use tone 192.8"]
    finally:
        db.close()


def test_non_automated_transcript_filter():
    assert not non_automated_transcript_text("[static only]")
    assert not non_automated_transcript_text("[inaudible]")
    assert not non_automated_transcript_text("Transcription failed: remote error")
    assert not non_automated_transcript_text("Transcription is in manual/no-op mode. Recording captured at x.wav.")
    assert not non_automated_transcript_text("Welcome to the K0RPT repeater.")
    assert not non_automated_transcript_text("Repeater ID K0RPT. Use tone 192.8.")
    assert not non_automated_transcript_text("Example Amateur Radio Club repeater K0RPT. Use tone 192.8.")
    assert not non_automated_transcript_text("K0RPT repeater Example City. Use tone 192.8.")
    assert non_automated_transcript_text("K0ABC checking into the morning net.")
    assert non_automated_transcript_text("Welcome to the K0RPT repeater. K0ABC checking in.")


def test_traffic_alert_suppress_phrases_are_case_insensitive():
    assert suppressed_by_phrase("K0RPT repeater Example City. Use tone 192.8.", ["example city"])
    assert not non_automated_transcript_text("K0ABC checking into the morning net.", ["K0ABC checking"])


def test_transcript_excerpt_removes_callsign_footer():
    excerpt = transcript_excerpt("K0ABC checking in.\n\nLikely callsigns detected: K0ABC")

    assert excerpt == "K0ABC checking in."


def test_traffic_alert_notification_creates_event_only_when_enabled(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        engine = KeywordEngine(db, NotificationService(db, AppConfig()))

        disabled = asyncio.run(
            engine.notify_traffic_transcript(
                source_id=10,
                repeater_id=None,
                text="K0ABC checking in.",
                repeater_name="K0RPT Main",
            )
        )
        assert disabled is None
        assert db.list_notification_events() == []

        db.set_traffic_alerts_enabled(True)
        automated = asyncio.run(
            engine.notify_traffic_transcript(
                source_id=11,
                repeater_id=None,
                text="Welcome to the K0RPT repeater.",
                repeater_name="K0RPT Main",
            )
        )
        assert automated is None
        assert db.list_notification_events() == []

        event_id = asyncio.run(
            engine.notify_traffic_transcript(
                source_id=12,
                repeater_id=None,
                text="K0ABC checking in.",
                repeater_name="K0RPT Main",
            )
        )

        assert event_id is not None
        event = db.get_notification_event(event_id)
        assert event
        assert event["source_type"] == "traffic"
        assert event["source_id"] == 12
        assert event["matched_text"] == "K0ABC checking in."
    finally:
        db.close()


def test_keyword_cooldown(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        config = AppConfig()
        engine = KeywordEngine(db, NotificationService(db, config))
        rule_id = db.create_keyword_rule(
            {
                "keyword": "emergency",
                "cooldown_minutes": 10,
                "notify_transcript": True,
                "notify_summary": True,
                "enabled": True,
            }
        )
        now = datetime(2026, 1, 1, tzinfo=UTC)
        first = engine.matching_rules("transcript", None, "emergency traffic", now=now)
        assert [match.rule["id"] for match in first] == [rule_id]

        db.add_notification_event(
            {
                "rule_id": rule_id,
                "source_type": "transcript",
                "source_id": 1,
                "title": "test",
                "body": "test",
                "matched_text": "emergency",
                "created_at": now.isoformat(timespec="seconds"),
            }
        )
        assert engine.matching_rules("transcript", None, "emergency traffic", now=now + timedelta(minutes=5)) == []
        assert engine.matching_rules("transcript", None, "emergency traffic", now=now + timedelta(minutes=11))
    finally:
        db.close()
