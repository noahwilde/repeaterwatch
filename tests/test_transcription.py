from __future__ import annotations

import asyncio

from app.config import AppConfig
from app.transcribe.whisper import (
    STATIC_ONLY_TEXT,
    TranscriptionService,
    build_transcription_prompt,
    finalize_transcript_result,
    low_confidence_text,
    normalize_spoken_callsigns,
    post_process_transcript,
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
