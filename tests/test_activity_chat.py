from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import AppConfig
from app.db import Database
from app.models import ActivityChatRequest
from app.summarize.chat import (
    ACTIVITY_CHAT_SYSTEM_PROMPT,
    ActivityChatService,
    build_activity_chat_prompt,
    plain_activity_chat_answer,
    select_activity_chat_context,
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


def test_activity_chat_prompt_uses_recent_grounded_sources(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745, "tone": "192.8"})
        now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
        recent_id = _recording_with_transcript(
            db,
            repeater_id,
            now - timedelta(minutes=20),
            "K0ABC asked K0XYZ about road conditions near the county line.",
        )
        _recording_with_transcript(
            db,
            repeater_id,
            now - timedelta(hours=3),
            "Old traffic outside the selected range.",
        )
        summary_id = db.add_summary(
            {
                "window_name": "hour",
                "repeater_id": repeater_id,
                "start_time": (now - timedelta(hours=1)).isoformat(timespec="seconds"),
                "end_time": now.isoformat(timespec="seconds"),
                "text": "K0ABC and K0XYZ discussed road conditions near the county line.",
                "model": "noop",
                "prompt_version": "test",
                "source_transcript_ids": [recent_id],
                "status": "completed",
            }
        )
        config = AppConfig()
        config.activity_chat.timezone = "UTC"

        context = select_activity_chat_context(db, config, hours=2, repeater_id=repeater_id, now=now)
        prompt = build_activity_chat_prompt(context, max_context_chars=30_000)

        assert "Use only the supplied Recent Activity Context as factual evidence" in ACTIVITY_CHAT_SYSTEM_PROMPT
        assert "Discuss only things that were actually said" in ACTIVITY_CHAT_SYSTEM_PROMPT
        assert "Use plain text only" in ACTIVITY_CHAT_SYSTEM_PROMPT
        assert "Do not use Markdown" in ACTIVITY_CHAT_SYSTEM_PROMPT
        assert "or emoji" in ACTIVITY_CHAT_SYSTEM_PROMPT
        assert "Evidence rules: answer only from the source items below" in prompt.context_text
        assert "K0ABC asked K0XYZ about road conditions" in prompt.context_text
        assert "Old traffic outside" not in prompt.context_text
        assert prompt.transcript_ids == [recent_id]
        assert prompt.summary_ids == [summary_id]
    finally:
        db.close()


def test_plain_activity_chat_answer_removes_markdown_and_emoji():
    answer = plain_activity_chat_answer(
        "# Update\n"
        "- **K0ABC** checked in. 👍\n"
        "1. [Details](https://example.test) were not in the transcript.\n"
        "```text\n"
        "coded\n"
        "```\n"
    )

    assert answer == "Update\nK0ABC checked in.\nDetails were not in the transcript.\ncoded"
    assert "#" not in answer
    assert "**" not in answer
    assert "👍" not in answer
    assert "[" not in answer
    assert "](" not in answer


def test_activity_chat_noop_records_skipped_usage(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        config = AppConfig()
        config.activity_chat.backend = "noop"
        service = ActivityChatService(db, config)

        response = asyncio.run(service.answer(ActivityChatRequest(message="What happened?", hours=1)))
        events = db.list_api_usage_events()

        assert "Activity chat is disabled" in response["answer"]
        assert response["source_counts"] == {"transcripts": 0, "summaries": 0}
        assert events[0]["call_type"] == "activity_chat"
        assert events[0]["status"] == "skipped"
        assert events[0]["reason"] == "disabled"
    finally:
        db.close()
