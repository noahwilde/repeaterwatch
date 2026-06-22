from __future__ import annotations

from datetime import UTC, datetime

from app.db import Database


def test_delete_recording_cascades_transcript(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        recording_id = db.add_recording(
            {
                "frequency_mhz": 146.745,
                "repeater_name": "K0RPT Main",
                "start_time": datetime.now(UTC).isoformat(timespec="seconds"),
                "duration_seconds": 1.0,
                "audio_path": str(tmp_path / "recording.wav"),
                "status": "completed",
            }
        )
        db.add_transcript(
            recording_id,
            text="K0RPT",
            original_text="K0RPT",
            confidence=0.9,
            low_confidence=False,
            backend="test",
            segments=[],
        )

        db.delete_recording(recording_id)

        assert db.get_recording(recording_id) is None
        assert db.get_transcript_for_recording(recording_id) is None
    finally:
        db.close()


def test_list_static_only_recordings_matches_current_transcript_text(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        static_recording_id = db.add_recording(
            {
                "frequency_mhz": 146.745,
                "repeater_name": "K0RPT Main",
                "start_time": datetime.now(UTC).isoformat(timespec="seconds"),
                "duration_seconds": 1.0,
                "audio_path": str(tmp_path / "static.wav"),
                "status": "completed",
            }
        )
        speech_recording_id = db.add_recording(
            {
                "frequency_mhz": 146.745,
                "repeater_name": "K0RPT Main",
                "start_time": datetime.now(UTC).isoformat(timespec="seconds"),
                "duration_seconds": 2.0,
                "audio_path": str(tmp_path / "speech.wav"),
                "status": "completed",
            }
        )
        corrected_recording_id = db.add_recording(
            {
                "frequency_mhz": 146.745,
                "repeater_name": "K0RPT Main",
                "start_time": datetime.now(UTC).isoformat(timespec="seconds"),
                "duration_seconds": 3.0,
                "audio_path": str(tmp_path / "corrected.wav"),
                "status": "completed",
            }
        )
        db.add_transcript(
            static_recording_id,
            text=" [STATIC ONLY] ",
            original_text=" [STATIC ONLY] ",
            confidence=None,
            low_confidence=True,
            backend="test",
            segments=[],
        )
        db.add_transcript(
            speech_recording_id,
            text="K0RPT",
            original_text="K0RPT",
            confidence=0.9,
            low_confidence=False,
            backend="test",
            segments=[],
        )
        corrected_transcript_id = db.add_transcript(
            corrected_recording_id,
            text="[static only]",
            original_text="[static only]",
            confidence=None,
            low_confidence=True,
            backend="test",
            segments=[],
        )
        db.update_transcript_correction(corrected_transcript_id, "Repeater ID K0RPT")

        static_recordings = db.list_static_only_recordings()

        assert [row["id"] for row in static_recordings] == [static_recording_id]
    finally:
        db.close()


def test_clear_summaries_and_notification_events(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        summary_id = db.add_summary(
            {
                "window_name": "today",
                "start_time": datetime.now(UTC).isoformat(timespec="seconds"),
                "end_time": datetime.now(UTC).isoformat(timespec="seconds"),
                "text": "summary",
                "model": "test",
                "prompt_version": "test",
            }
        )
        event_id = db.add_notification_event(
            {
                "source_type": "test",
                "source_id": 0,
                "title": "test",
                "body": "body",
                "matched_text": "manual test",
            }
        )

        assert db.get_summary(summary_id)
        assert db.get_notification_event(event_id)
        assert db.clear_summaries() == 1
        assert db.clear_notification_events() == 1

        assert db.list_summaries() == []
        assert db.list_notification_events() == []
    finally:
        db.close()
