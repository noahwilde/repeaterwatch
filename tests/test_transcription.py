from __future__ import annotations

import asyncio

from app.config import AppConfig
from app.db import Database
from app.transcribe.whisper import (
    RemoteTranscriptionRateLimited,
    STATIC_ONLY_TEXT,
    TranscriptResult,
    TranscriptionService,
    TranscriptionWorker,
    build_transcription_prompt,
    finalize_transcript_result,
    low_confidence_text,
    normalize_spoken_callsigns,
    post_process_transcript,
)


class _RateLimitedTranscriptionService:
    async def transcribe(self, audio_path, recording=None):
        raise RemoteTranscriptionRateLimited(retry_after_seconds=30)


class _FallbackTranscriptionService(TranscriptionService):
    def __init__(self, config: AppConfig):
        super().__init__(config)
        self.calls: list[str] = []

    async def _remote_transcript(
        self,
        audio_path,
        recording=None,
        model=None,
        backend="openai-compatible",
        force_low_confidence=False,
        fallback_from_model=None,
        fallback_reason=None,
        fallback_primary_attempted=False,
    ):
        model_name = model or self.config.transcription.remote_model
        self.calls.append(model_name)
        if model_name == self.config.transcription.remote_model:
            raise RemoteTranscriptionRateLimited(retry_after_seconds=30, model=model_name)
        return TranscriptResult(
            text="K0FYB monitoring.",
            original_text="K0FYB monitoring.",
            confidence=None,
            low_confidence=force_low_confidence,
            backend=backend,
            model=model_name,
            fallback_from_model=fallback_from_model,
            fallback_reason=fallback_reason,
            fallback_primary_attempted=fallback_primary_attempted,
        )


class _FallbackResultTranscriptionService:
    async def transcribe(self, audio_path, recording=None):
        return TranscriptResult(
            text="K0FYB monitoring.",
            original_text="K0FYB monitoring.",
            confidence=None,
            low_confidence=True,
            backend="openai-compatible-fallback",
            model="gpt-4o-mini-transcribe",
            fallback_from_model="gpt-4o-transcribe",
            fallback_reason="primary rate limited",
            fallback_primary_attempted=True,
        )


def test_transcription_prompt_includes_repeater_context():
    prompt = build_transcription_prompt(
        {
            "configured_repeater_name": "K0RPT Main",
            "frequency_mhz": 146.745,
            "repeater_tone": "123.0",
        }
    )

    assert "K0RPT Main" in prompt
    assert "146.745 MHz" in prompt
    assert "123.0" in prompt
    assert "Known repeater callsign(s): K0RPT" in prompt
    assert "reference context only" in prompt
    assert "Do not invent welcome messages" in prompt
    assert "Example Amateur Radio Club" not in prompt
    assert "Welcome to the K0RPT repeater" not in prompt
    assert "[static only]" in prompt


def test_post_process_normalizes_known_callsign_rendering():
    processed = post_process_transcript(
        "Repeater ID K zero R P T. Use tone one ninety two point eight.",
        known_callsigns=["K0RPT"],
    )
    hyphenated = post_process_transcript("Use tone one ninety-two point eight.")

    assert "K0RPT" in processed
    assert "192.8" in processed
    assert "192.8" in hyphenated
    assert "Likely callsigns detected: K0RPT" in processed


def test_post_process_normalizes_phonetic_callsigns():
    processed = post_process_transcript("This is kilo zero xray yankee zulu monitoring.")

    assert "This is K0XYZ monitoring." in processed
    assert "kilo zero xray yankee zulu" not in processed.casefold()
    assert "Likely callsigns detected: K0XYZ" in processed


def test_post_process_corrects_near_known_callsign_suffix_miss():
    processed = post_process_transcript("K0FYD monitoring.", known_callsigns=["K0FYB"])

    assert "K0FYB monitoring." in processed
    assert "K0FYD" not in processed


def test_spoken_callsign_normalization_ignores_non_callsign_phrases():
    assert normalize_spoken_callsigns("alpha bravo charlie delta") == "alpha bravo charlie delta"
    assert normalize_spoken_callsigns("one two three four") == "one two three four"


def test_low_confidence_text_marks_static_and_inaudible():
    assert low_confidence_text("[static only]")
    assert low_confidence_text("[inaudible]")
    assert not low_confidence_text("Welcome to the K0RPT repeater.")


def test_short_prompt_like_hallucination_is_marked_static_only():
    result = finalize_transcript_result(
        original="Welcome to the K0RPT repeater.",
        recording={"duration_seconds": 1.0},
        confidence=None,
        low_confidence=False,
        backend="openai-compatible",
        segments=[],
    )

    assert result.text == STATIC_ONLY_TEXT
    assert result.original_text == "Welcome to the K0RPT repeater."
    assert result.low_confidence is True


def test_longer_prompt_like_transcript_is_not_rewritten():
    result = finalize_transcript_result(
        original="Welcome to the K0RPT repeater.",
        recording={"duration_seconds": 6.0},
        confidence=None,
        low_confidence=False,
        backend="openai-compatible",
        segments=[],
    )

    assert "Welcome to the K0RPT repeater" in result.text
    assert result.low_confidence is False


def test_empty_transcript_is_marked_static_only():
    result = finalize_transcript_result(
        original="",
        recording={"duration_seconds": 1.0},
        confidence=None,
        low_confidence=False,
        backend="openai-compatible",
        segments=[],
    )

    assert result.text == STATIC_ONLY_TEXT
    assert result.low_confidence is True


def test_remote_transcription_skips_short_recording_before_api_key_check():
    config = AppConfig()
    config.transcription.backend = "openai-compatible"
    config.transcription.remote_min_duration_seconds = 2.0

    result = asyncio.run(
        TranscriptionService(config).transcribe(
            "missing.wav",
            {"duration_seconds": 1.0},
        )
    )

    assert result.text == STATIC_ONLY_TEXT
    assert result.original_text == STATIC_ONLY_TEXT
    assert result.backend == "openai-compatible-skipped"
    assert result.low_confidence is True


def test_remote_transcription_uses_low_confidence_fallback_after_primary_rate_limit():
    config = AppConfig()
    config.transcription.backend = "openai-compatible"
    config.transcription.remote_model = "gpt-4o-transcribe"
    config.transcription.remote_fallback_model = "gpt-4o-mini-transcribe"
    service = _FallbackTranscriptionService(config)

    first = asyncio.run(service.transcribe("missing.wav", {"duration_seconds": 5.0}))
    second = asyncio.run(service.transcribe("missing.wav", {"duration_seconds": 5.0}))

    assert first.backend == "openai-compatible-fallback"
    assert first.model == "gpt-4o-mini-transcribe"
    assert first.fallback_from_model == "gpt-4o-transcribe"
    assert first.fallback_primary_attempted is True
    assert first.low_confidence is True
    assert second.backend == "openai-compatible-fallback"
    assert second.fallback_primary_attempted is False
    assert service.calls == ["gpt-4o-transcribe", "gpt-4o-mini-transcribe", "gpt-4o-mini-transcribe"]


def test_transcription_worker_records_short_remote_skip_usage(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        audio_path = tmp_path / "short.wav"
        audio_path.write_bytes(b"not really a wav")
        recording_id = db.add_recording(
            {
                "frequency_mhz": 146.745,
                "repeater_name": "K0RPT Main",
                "start_time": "2026-06-22T12:00:00+00:00",
                "duration_seconds": 1.0,
                "audio_path": str(audio_path),
                "status": "completed",
            }
        )
        recording = db.get_recording(recording_id)
        config = AppConfig()
        config.transcription.backend = "openai-compatible"
        config.transcription.remote_min_duration_seconds = 2.0
        worker = TranscriptionWorker(db, config)

        asyncio.run(worker.process_recording(recording))
        usage_events = db.list_api_usage_events()

        assert usage_events[0]["call_type"] == "transcription"
        assert usage_events[0]["status"] == "skipped"
        assert usage_events[0]["reason"] == "short_recording"
        assert usage_events[0]["audio_duration_seconds"] == 1.0
    finally:
        db.close()


def test_transcription_worker_leaves_rate_limited_recording_pending(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        audio_path = tmp_path / "traffic.wav"
        audio_path.write_bytes(b"not really a wav")
        recording_id = db.add_recording(
            {
                "frequency_mhz": 146.745,
                "repeater_name": "K0RPT Main",
                "start_time": "2026-06-22T12:00:00+00:00",
                "duration_seconds": 5.0,
                "audio_path": str(audio_path),
                "status": "completed",
            }
        )
        config = AppConfig()
        config.transcription.backend = "openai-compatible"
        worker = TranscriptionWorker(db, config)
        worker.service = _RateLimitedTranscriptionService()

        count = asyncio.run(worker.process_pending(limit=5))
        usage_events = db.list_api_usage_events()

        assert count == 0
        assert worker.remote_backoff_until > 0
        assert db.get_transcript_for_recording(recording_id) is None
        assert [row["id"] for row in db.pending_recordings_for_transcription()] == [recording_id]
        assert usage_events[0]["call_type"] == "transcription"
        assert usage_events[0]["status"] == "error"
        assert usage_events[0]["reason"] == "remote_transcription_rate_limited"
    finally:
        db.close()


def test_transcription_worker_records_fallback_usage(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        audio_path = tmp_path / "traffic.wav"
        audio_path.write_bytes(b"not really a wav")
        recording_id = db.add_recording(
            {
                "frequency_mhz": 146.745,
                "repeater_name": "K0RPT Main",
                "start_time": "2026-06-22T12:00:00+00:00",
                "duration_seconds": 5.0,
                "audio_path": str(audio_path),
                "status": "completed",
            }
        )
        config = AppConfig()
        config.transcription.backend = "openai-compatible"
        config.transcription.remote_model = "gpt-4o-transcribe"
        worker = TranscriptionWorker(db, config)
        worker.service = _FallbackResultTranscriptionService()

        transcript_id = asyncio.run(worker.process_recording(db.get_recording(recording_id)))
        usage_events = db.list_api_usage_events()
        transcript = db.get_transcript_for_recording(recording_id)

        assert transcript_id == transcript["id"]
        assert transcript["backend"] == "openai-compatible-fallback"
        assert transcript["low_confidence"] is True
        assert [event["status"] for event in usage_events] == ["success", "error"]
        assert usage_events[0]["model"] == "gpt-4o-mini-transcribe"
        assert usage_events[0]["reason"] == "remote_transcription_fallback"
        assert usage_events[1]["model"] == "gpt-4o-transcribe"
        assert usage_events[1]["reason"] == "remote_transcription_rate_limited"
    finally:
        db.close()
