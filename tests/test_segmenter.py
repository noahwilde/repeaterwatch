from __future__ import annotations

from array import array
from datetime import UTC, datetime, timedelta

import pytest

from app.audio.segmenter import VoxSegmenter
from app.config import VoxConfig


def _pcm_chunk(value: int = 3000, seconds: float = 0.25, sample_rate: int = 24_000) -> bytes:
    samples = array("h", [value] * int(sample_rate * seconds))
    return samples.tobytes()


def test_squelched_output_gap_splits_recordings():
    config = VoxConfig(
        pre_roll_seconds=0,
        post_silence_seconds=1.0,
        min_duration_seconds=0.1,
        max_duration_seconds=180.0,
        threshold=0.018,
        sample_rate=24_000,
        chunk_seconds=0.25,
    )
    segmenter = VoxSegmenter(config)
    chunk = _pcm_chunk(sample_rate=config.sample_rate)
    start = datetime(2026, 1, 1, tzinfo=UTC)

    assert segmenter.process(chunk, now=start) == []
    assert segmenter.process(chunk, now=start + timedelta(seconds=0.25)) == []

    emitted = segmenter.process(chunk, now=start + timedelta(seconds=5))

    assert len(emitted) == 1
    assert emitted[0].duration_seconds == pytest.approx(0.5)
    assert emitted[0].end_time == start + timedelta(seconds=0.25)

    remaining = segmenter.flush(now=start + timedelta(seconds=5.25))
    assert len(remaining) == 1
    assert remaining[0].duration_seconds == pytest.approx(0.25)
