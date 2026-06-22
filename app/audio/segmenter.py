from __future__ import annotations

import math
import wave
from array import array
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import VoxConfig


@dataclass
class AudioSegment:
    chunks: list[bytes]
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    level_proxy: float


def pcm16_rms_level(chunk: bytes) -> float:
    if len(chunk) < 2:
        return 0.0
    usable = chunk[: len(chunk) - (len(chunk) % 2)]
    samples = array("h")
    samples.frombytes(usable)
    if not samples:
        return 0.0
    square_sum = sum((sample / 32768.0) ** 2 for sample in samples)
    return math.sqrt(square_sum / len(samples))


class VoxSegmenter:
    """Conservative PCM16 mono VOX segmenter with pre-roll and post-silence."""

    def __init__(self, config: VoxConfig):
        self.config = config
        self.bytes_per_second = config.sample_rate * 2
        self.pre_roll_bytes = int(self.bytes_per_second * config.pre_roll_seconds)
        self.max_segment_bytes = int(self.bytes_per_second * config.max_duration_seconds)
        self.min_segment_bytes = int(self.bytes_per_second * config.min_duration_seconds)
        self.post_silence_bytes = int(self.bytes_per_second * config.post_silence_seconds)
        max_preroll_chunks = max(1, math.ceil(config.pre_roll_seconds / config.chunk_seconds))
        self.pre_roll: deque[bytes] = deque(maxlen=max_preroll_chunks)
        self.active_chunks: list[bytes] = []
        self.active_start: datetime | None = None
        self.silence_bytes = 0
        self.active_level_sum = 0.0
        self.active_level_count = 0
        self.active_last_time: datetime | None = None

    def process(self, chunk: bytes, now: datetime | None = None) -> list[AudioSegment]:
        now = now or datetime.now(UTC)
        emitted: list[AudioSegment] = []
        level = pcm16_rms_level(chunk)
        active = level >= self.config.threshold
        chunk_seconds = len(chunk) / self.bytes_per_second if self.bytes_per_second else 0.0

        if self.active_start is not None and self.active_last_time is not None:
            gap_seconds = (now - self.active_last_time).total_seconds() - chunk_seconds
            if gap_seconds >= self.config.post_silence_seconds:
                active_bytes = sum(len(part) for part in self.active_chunks)
                if active_bytes >= self.min_segment_bytes:
                    emitted.append(self._finish(self.active_last_time))
                else:
                    self._reset()

        if self.active_start is None:
            self.pre_roll.append(chunk)
            if active:
                self.active_start = now
                self.active_chunks = list(self.pre_roll)
                self.active_last_time = now
                self.silence_bytes = 0
                self.active_level_sum = level
                self.active_level_count = 1
            return emitted

        self.active_chunks.append(chunk)
        self.active_last_time = now
        self.active_level_sum += level
        self.active_level_count += 1
        if active:
            self.silence_bytes = 0
        else:
            self.silence_bytes += len(chunk)

        active_bytes = sum(len(part) for part in self.active_chunks)
        if active_bytes >= self.max_segment_bytes:
            emitted.append(self._finish(now))
        elif self.silence_bytes >= self.post_silence_bytes:
            if active_bytes >= self.min_segment_bytes:
                emitted.append(self._finish(now))
            else:
                self._reset()
        return emitted

    def flush(self, now: datetime | None = None) -> list[AudioSegment]:
        if self.active_start is None:
            return []
        active_bytes = sum(len(part) for part in self.active_chunks)
        if active_bytes < self.min_segment_bytes:
            self._reset()
            return []
        return [self._finish(now or datetime.now(UTC))]

    def _finish(self, end_time: datetime) -> AudioSegment:
        assert self.active_start is not None
        chunks = self.active_chunks
        total_bytes = sum(len(part) for part in chunks)
        duration = total_bytes / self.bytes_per_second if self.bytes_per_second else 0.0
        level = self.active_level_sum / max(1, self.active_level_count)
        segment = AudioSegment(
            chunks=chunks,
            start_time=self.active_start,
            end_time=end_time,
            duration_seconds=duration,
            level_proxy=level,
        )
        self._reset()
        return segment

    def _reset(self) -> None:
        self.pre_roll.clear()
        self.active_chunks = []
        self.active_start = None
        self.active_last_time = None
        self.silence_bytes = 0
        self.active_level_sum = 0.0
        self.active_level_count = 0


def write_wav(path: str | Path, chunks: list[bytes], sample_rate: int) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for chunk in chunks:
            wav.writeframes(chunk)
