from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import AppConfig
from app.db import Database

logger = logging.getLogger(__name__)

CALLSIGN_RE = re.compile(r"\b(?:[AKNW][A-Z]?[0-9][A-Z]{1,3}|[A-Z]{1,2}[0-9][A-Z]{1,3})\b")
CALLSIGN_VARIANT_DIGITS = {
    "0": r"(?:0|O|OH|ZERO)",
    "1": r"(?:1|ONE)",
    "2": r"(?:2|TWO)",
    "3": r"(?:3|THREE)",
    "4": r"(?:4|FOUR)",
    "5": r"(?:5|FIVE)",
    "6": r"(?:6|SIX)",
    "7": r"(?:7|SEVEN)",
    "8": r"(?:8|EIGHT)",
    "9": r"(?:9|NINE|NINER)",
}
SPOKEN_CALLSIGN_TOKEN_VALUES = {
    "alfa": "A",
    "alpha": "A",
    "bravo": "B",
    "charlie": "C",
    "delta": "D",
    "echo": "E",
    "foxtrot": "F",
    "golf": "G",
    "hotel": "H",
    "india": "I",
    "juliet": "J",
    "juliett": "J",
    "kilo": "K",
    "lima": "L",
    "mike": "M",
    "november": "N",
    "oscar": "O",
    "papa": "P",
    "quebec": "Q",
    "romeo": "R",
    "sierra": "S",
    "tango": "T",
    "uniform": "U",
    "victor": "V",
    "whiskey": "W",
    "whisky": "W",
    "xray": "X",
    "yankee": "Y",
    "zulu": "Z",
    "zed": "Z",
    "zero": "0",
    "oh": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "niner": "9",
    "0": "0",
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    "6": "6",
    "7": "7",
    "8": "8",
    "9": "9",
}
SPOKEN_CALLSIGN_TOKEN_RE = re.compile(
    r"\b(?:"
    r"fox[-\s]+trot|x[-\s]+ray|"
    r"juliett|november|whiskey|charlie|foxtrot|uniform|victor|quebec|"
    r"sierra|bravo|delta|alpha|hotel|india|juliet|oscar|romeo|tango|"
    r"whisky|yankee|three|seven|eight|niner|alfa|echo|golf|kilo|lima|mike|"
    r"papa|xray|zulu|zero|four|five|nine|zed|one|two|six|oh|[0-9]"
    r")\b",
    re.IGNORECASE,
)
SPOKEN_CALLSIGN_SEPARATOR_RE = re.compile(r"^[\s,-]*$")
SPOKEN_DECIMAL_REPLACEMENTS = (
    (re.compile(r"\bone\s+ninety[-\s]+two\s+point\s+eight\b", re.IGNORECASE), "192.8"),
)
REMOTE_AUDIO_FILTER = "highpass=f=250,lowpass=f=3600,afftdn=nf=-25,dynaudnorm=f=75:g=15,volume=6dB"
STATIC_ONLY_TEXT = "[static only]"
SHORT_RECORDING_HALLUCINATION_SECONDS = 2.0
REMOTE_RATE_LIMIT_BACKOFF_SECONDS = 15 * 60
PROMPT_LIKE_HALLUCINATION_RE = (
    re.compile(r"\bwelcome\s+to\s+(?:the\s+)?.{0,40}\brepeater\b", re.IGNORECASE),
    re.compile(r"\bamateur\s+radio\s+club\b", re.IGNORECASE),
    re.compile(r"\buse\s+tone\s+(?:[0-9]+(?:\.[0-9]+)?|[a-z]+(?:[-\s]+[a-z]+){0,5})\b", re.IGNORECASE),
)


class RemoteTranscriptionRateLimited(RuntimeError):
    def __init__(self, retry_after_seconds: float | None = None):
        super().__init__(
            "OpenAI-compatible transcription provider is rate limiting requests. "
            "Recording will remain pending and retry later."
        )
        self.retry_after_seconds = retry_after_seconds


@dataclass
class TranscriptResult:
    text: str
    original_text: str
    confidence: float | None
    low_confidence: bool
    backend: str
    segments: list[dict[str, Any]] = field(default_factory=list)


def detect_callsigns(text: str) -> list[str]:
    candidates = {match.group(0).upper() for match in CALLSIGN_RE.finditer(text.upper())}
    return sorted(candidates)


def _spoken_callsign_token_value(value: str) -> str | None:
    key = re.sub(r"[^a-z0-9]", "", value.casefold())
    return SPOKEN_CALLSIGN_TOKEN_VALUES.get(key)


def normalize_spoken_callsigns(text: str) -> str:
    token_matches = list(SPOKEN_CALLSIGN_TOKEN_RE.finditer(text))
    if not token_matches:
        return text

    replacements: list[tuple[int, int, str]] = []
    index = 0
    while index < len(token_matches):
        chars: list[str] = []
        phrase_start = token_matches[index].start()
        best: tuple[int, int, str, int] | None = None

        for cursor in range(index, min(index + 6, len(token_matches))):
            if cursor > index:
                separator = text[token_matches[cursor - 1].end():token_matches[cursor].start()]
                if not SPOKEN_CALLSIGN_SEPARATOR_RE.fullmatch(separator):
                    break
            value = _spoken_callsign_token_value(token_matches[cursor].group(0))
            if not value:
                break
            chars.append(value)
            candidate = "".join(chars)
            if len(candidate) >= 3 and CALLSIGN_RE.fullmatch(candidate):
                best = (phrase_start, token_matches[cursor].end(), candidate, cursor)

        if best:
            replacements.append((best[0], best[1], best[2]))
            index = best[3] + 1
        else:
            index += 1

    if not replacements:
        return text

    output: list[str] = []
    position = 0
    for start, end, replacement in replacements:
        output.append(text[position:start])
        output.append(replacement)
        position = end
    output.append(text[position:])
    return "".join(output)


def callsign_variant_pattern(callsign: str) -> re.Pattern[str] | None:
    normalized = callsign.upper()
    if not CALLSIGN_RE.fullmatch(normalized):
        return None
    parts = [CALLSIGN_VARIANT_DIGITS.get(char, re.escape(char)) for char in normalized]
    return re.compile(r"\b" + r"[\s,-]*".join(parts) + r"\b", re.IGNORECASE)


def normalize_known_callsign_variants(text: str, known_callsigns: list[str] | None = None) -> str:
    output = text
    for callsign in sorted(set(known_callsigns or [])):
        pattern = callsign_variant_pattern(callsign)
        if pattern:
            output = pattern.sub(callsign.upper(), output)
    return output


def post_process_transcript(text: str, known_callsigns: list[str] | None = None) -> str:
    text = normalize_spoken_callsigns(text)
    text = normalize_known_callsign_variants(text, known_callsigns)
    for pattern, replacement in SPOKEN_DECIMAL_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    callsigns = detect_callsigns(text)
    if not callsigns:
        return text.strip()
    suffix = "Likely callsigns detected: " + ", ".join(callsigns)
    return f"{text.strip()}\n\n{suffix}".strip()


def known_callsigns_from_context(recording: dict[str, Any] | None) -> list[str]:
    if not recording:
        return []
    values = [
        recording.get("configured_repeater_name"),
        recording.get("repeater_name"),
        recording.get("name"),
    ]
    callsigns: set[str] = set()
    for value in values:
        if value:
            callsigns.update(detect_callsigns(str(value)))
    return sorted(callsigns)


def build_transcription_prompt(recording: dict[str, Any] | None = None) -> str:
    if not recording:
        return (
            "Amateur radio FM repeater audio. Transcribe only speech that is actually audible. "
            "Use ham radio callsign formatting only when clear."
        )
    name = recording.get("configured_repeater_name") or recording.get("repeater_name") or "unknown repeater"
    frequency = recording.get("frequency_mhz") or recording.get("configured_frequency_mhz")
    tone = recording.get("repeater_tone") or recording.get("tone") or "not configured"
    location = recording.get("repeater_location") or recording.get("location")
    coverage_area = recording.get("repeater_coverage_area") or recording.get("coverage_area")
    repeater_type = recording.get("repeater_type")
    notes = recording.get("repeater_notes") or recording.get("notes")
    known_callsigns = known_callsigns_from_context(recording)
    callsign_hint = ", ".join(known_callsigns) if known_callsigns else "none configured"
    parts = [
        "Amateur radio FM repeater audio.",
        "Transcribe only words that are actually audible in this recording.",
        "The repeater metadata is reference context only, not expected transcript text.",
        f"Repeater name: {name}.",
        f"Frequency: {frequency} MHz." if frequency else "Frequency: unknown.",
        f"Tone/CTCSS: {tone}.",
        f"Location: {location}." if location else "",
        f"Coverage area: {coverage_area}." if coverage_area else "",
        f"Repeater type: {repeater_type}." if repeater_type else "",
        f"Notes: {notes}." if notes else "",
        f"Known repeater callsign(s): {callsign_hint}.",
        "Use a known callsign only when the audio clearly supports it.",
        "Do not invent welcome messages, repeater IDs, callsigns, tones, or club names from metadata.",
        "If the audio is only static, a beep, squelch tail, or no speech is audible, output exactly [static only]. "
        "Use [inaudible] only for unclear portions inside otherwise intelligible speech.",
    ]
    return " ".join(parts)


def low_confidence_text(text: str) -> bool:
    normalized = text.strip().casefold()
    return normalized in {"", STATIC_ONLY_TEXT, "[inaudible]"} or normalized.startswith("[inaudible]")


def _recording_duration_seconds(recording: dict[str, Any] | None) -> float | None:
    if not recording:
        return None
    try:
        return float(recording.get("duration_seconds"))
    except (TypeError, ValueError):
        return None


def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    retry_after = response.headers.get("retry-after")
    if not retry_after:
        return None
    try:
        return max(1.0, float(retry_after))
    except ValueError:
        return None


def prompt_like_hallucination_on_short_recording(text: str, recording: dict[str, Any] | None) -> bool:
    duration = _recording_duration_seconds(recording)
    if duration is None or duration > SHORT_RECORDING_HALLUCINATION_SECONDS:
        return False
    return any(pattern.search(text) for pattern in PROMPT_LIKE_HALLUCINATION_RE)


def finalize_transcript_result(
    original: str,
    recording: dict[str, Any] | None,
    confidence: float | None,
    low_confidence: bool,
    backend: str,
    segments: list[dict[str, Any]] | None = None,
) -> TranscriptResult:
    processed = post_process_transcript(original, known_callsigns_from_context(recording))
    if not processed.strip() or prompt_like_hallucination_on_short_recording(processed, recording):
        return TranscriptResult(
            text=STATIC_ONLY_TEXT,
            original_text=original,
            confidence=confidence,
            low_confidence=True,
            backend=backend,
            segments=segments or [],
        )
    return TranscriptResult(
        text=processed,
        original_text=original,
        confidence=confidence,
        low_confidence=low_confidence or low_confidence_text(processed),
        backend=backend,
        segments=segments or [],
    )


def prepare_remote_audio(audio_path: str | Path) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    source = Path(audio_path)
    if shutil.which("ffmpeg") is None:
        return source, None
    temp_dir = tempfile.TemporaryDirectory(prefix="repeaterwatch-transcribe-")
    output = Path(temp_dir.name) / f"{source.stem}.voice.wav"
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        "24000",
        "-af",
        REMOTE_AUDIO_FILTER,
        str(output),
    ]
    try:
        subprocess.run(command, check=True)
    except Exception:
        logger.exception("Audio cleanup failed for %s; sending original audio", source)
        temp_dir.cleanup()
        return source, None
    return output, temp_dir


class TranscriptionService:
    def __init__(self, config: AppConfig):
        self.config = config
        self._whisper_model: Any | None = None

    async def transcribe(self, audio_path: str | Path, recording: dict[str, Any] | None = None) -> TranscriptResult:
        backend = self.config.transcription.backend
        if backend == "noop":
            return self._noop_transcript(audio_path)
        if backend == "faster-whisper":
            return await asyncio.to_thread(self._faster_whisper_transcript, audio_path, recording)
        if backend == "openai-compatible":
            short_result = self._short_recording_static_transcript(recording)
            if short_result:
                return short_result
            return await self._remote_transcript(audio_path, recording)
        raise ValueError(f"Unknown transcription backend: {backend}")

    def _noop_transcript(self, audio_path: str | Path) -> TranscriptResult:
        text = (
            "Transcription is in manual/no-op mode. "
            f"Recording captured at {Path(audio_path).name}; configure faster-whisper or an OpenAI-compatible API "
            "to generate speech text."
        )
        return TranscriptResult(
            text=text,
            original_text=text,
            confidence=None,
            low_confidence=True,
            backend="noop",
            segments=[],
        )

    def _short_recording_static_transcript(self, recording: dict[str, Any] | None) -> TranscriptResult | None:
        minimum_seconds = self.config.transcription.remote_min_duration_seconds
        duration = _recording_duration_seconds(recording)
        if minimum_seconds <= 0 or duration is None or duration >= minimum_seconds:
            return None
        logger.info(
            "Skipping remote transcription for %.2fs recording below %.2fs minimum",
            duration,
            minimum_seconds,
        )
        return TranscriptResult(
            text=STATIC_ONLY_TEXT,
            original_text=STATIC_ONLY_TEXT,
            confidence=None,
            low_confidence=True,
            backend="openai-compatible-skipped",
            segments=[],
        )

    def _faster_whisper_transcript(self, audio_path: str | Path, recording: dict[str, Any] | None = None) -> TranscriptResult:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is not installed. Install repeaterwatch[transcribe].") from exc

        if self._whisper_model is None:
            self._whisper_model = WhisperModel(
                self.config.transcription.model,
                compute_type=self.config.transcription.compute_type,
            )
        segments_iter, info = self._whisper_model.transcribe(
            str(audio_path),
            language=self.config.transcription.language,
            vad_filter=True,
            initial_prompt=build_transcription_prompt(recording),
        )
        segments: list[dict[str, Any]] = []
        text_parts: list[str] = []
        confidences: list[float] = []
        for segment in segments_iter:
            segment_text = segment.text.strip()
            if not segment_text:
                continue
            confidence = None
            if getattr(segment, "avg_logprob", None) is not None:
                confidence = max(0.0, min(1.0, 1.0 + float(segment.avg_logprob)))
                confidences.append(confidence)
            text_parts.append(segment_text)
            segments.append(
                {
                    "start_seconds": float(segment.start),
                    "end_seconds": float(segment.end),
                    "text": segment_text,
                    "confidence": confidence,
                }
            )
        original = " ".join(text_parts).strip()
        average_confidence = sum(confidences) / len(confidences) if confidences else None
        low_confidence = bool(average_confidence is not None and average_confidence < 0.45)
        if getattr(info, "language_probability", None) is not None and info.language_probability < 0.5:
            low_confidence = True
        return finalize_transcript_result(
            original=original,
            recording=recording,
            confidence=average_confidence,
            low_confidence=low_confidence,
            backend="faster-whisper",
            segments=segments,
        )

    async def _remote_transcript(self, audio_path: str | Path, recording: dict[str, Any] | None = None) -> TranscriptResult:
        api_key = os.getenv(self.config.transcription.remote_api_key_env, "")
        if not api_key:
            raise RuntimeError(f"{self.config.transcription.remote_api_key_env} is not set")
        base_url = self.config.transcription.remote_base_url.rstrip("/")
        url = f"{base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "model": self.config.transcription.remote_model,
            "prompt": build_transcription_prompt(recording),
            "response_format": "json",
        }
        if self.config.transcription.language:
            data["language"] = self.config.transcription.language
        prepared_path, temp_dir = prepare_remote_audio(audio_path)
        try:
            with prepared_path.open("rb") as handle:
                files = {"file": (prepared_path.name, handle, "audio/wav")}
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(url, headers=headers, data=data, files=files)
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429:
                            raise RemoteTranscriptionRateLimited(_retry_after_seconds(exc.response)) from exc
                        raise
        finally:
            if temp_dir:
                temp_dir.cleanup()
        payload = response.json()
        original = str(payload.get("text", "")).strip()
        return finalize_transcript_result(
            original=original,
            recording=recording,
            confidence=None,
            low_confidence=low_confidence_text(original),
            backend="openai-compatible",
            segments=[],
        )


class TranscriptionWorker:
    def __init__(self, db: Database, config: AppConfig, keyword_engine: Any | None = None):
        self.db = db
        self.config = config
        self.service = TranscriptionService(config)
        self.keyword_engine = keyword_engine
        self.stop_event = asyncio.Event()
        self.remote_backoff_until = 0.0

    async def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                await self.process_pending(limit=5)
            except Exception:
                logger.exception("Transcription worker pass failed")
            await asyncio.sleep(self.config.transcription.poll_seconds)

    def stop(self) -> None:
        self.stop_event.set()

    async def process_pending(self, limit: int = 10) -> int:
        count = 0
        if self._remote_backoff_active():
            return count
        for recording in self.db.pending_recordings_for_transcription(limit):
            try:
                await self.process_recording(recording)
            except RemoteTranscriptionRateLimited:
                break
            count += 1
        return count

    def _remote_backoff_active(self) -> bool:
        return self.config.transcription.backend == "openai-compatible" and time.monotonic() < self.remote_backoff_until

    def _start_remote_backoff(self, exc: RemoteTranscriptionRateLimited) -> float:
        seconds = exc.retry_after_seconds or REMOTE_RATE_LIMIT_BACKOFF_SECONDS
        seconds = max(1.0, min(float(seconds), 60 * 60))
        self.remote_backoff_until = time.monotonic() + seconds
        return seconds

    async def process_recording(self, recording: dict[str, Any]) -> int:
        audio_path = Path(recording["audio_path"])
        repeater_id = recording.get("repeater_id")
        usage_started: float | None = None
        usage_recorded = False
        try:
            if not audio_path.exists():
                raise FileNotFoundError(audio_path)
            recording_context = dict(recording)
            if repeater_id is not None:
                repeater = self.db.get_repeater(int(repeater_id))
                if repeater:
                    recording_context.update(
                        {
                            "configured_repeater_name": repeater.get("name"),
                            "configured_frequency_mhz": repeater.get("frequency_mhz"),
                            "repeater_tone": repeater.get("tone"),
                            "repeater_location": repeater.get("location"),
                            "repeater_coverage_area": repeater.get("coverage_area"),
                            "repeater_type": repeater.get("repeater_type"),
                            "repeater_notes": repeater.get("notes"),
                        }
                    )
            if self.config.transcription.backend == "openai-compatible":
                usage_started = time.monotonic()
            result = await self.service.transcribe(audio_path, recording_context)
            if usage_started is not None:
                status = "skipped" if result.backend == "openai-compatible-skipped" else "success"
                self.db.add_api_usage_event(
                    {
                        "provider": "openai-compatible",
                        "call_type": "transcription",
                        "operation": "recording",
                        "model": self.config.transcription.remote_model,
                        "status": status,
                        "source_type": "recording",
                        "source_id": int(recording["id"]),
                        "repeater_id": repeater_id,
                        "input_count": 1,
                        "audio_duration_seconds": _recording_duration_seconds(recording_context),
                        "elapsed_ms": int((time.monotonic() - usage_started) * 1000),
                        "reason": "short_recording" if status == "skipped" else "remote_transcription",
                        "metadata": {
                            "recording_start_time": recording.get("start_time"),
                            "repeater_name": recording.get("repeater_name"),
                        },
                    }
                )
                usage_recorded = True
            transcript_id = self.db.add_transcript(
                recording_id=int(recording["id"]),
                text=result.text,
                original_text=result.original_text,
                confidence=result.confidence,
                low_confidence=result.low_confidence,
                backend=result.backend,
                segments=result.segments,
                status="completed",
            )
            if self.keyword_engine:
                await self.keyword_engine.notify_traffic_transcript(
                    source_id=transcript_id,
                    repeater_id=repeater_id,
                    text=result.text,
                    repeater_name=recording.get("repeater_name", "Repeater"),
                )
                await self.keyword_engine.evaluate_and_notify(
                    source_type="transcript",
                    source_id=transcript_id,
                    repeater_id=repeater_id,
                    text=result.text,
                    repeater_name=recording.get("repeater_name", "Repeater"),
                )
            return transcript_id
        except RemoteTranscriptionRateLimited as exc:
            if usage_started is not None and not usage_recorded:
                self.db.add_api_usage_event(
                    {
                        "provider": "openai-compatible",
                        "call_type": "transcription",
                        "operation": "recording",
                        "model": self.config.transcription.remote_model,
                        "status": "error",
                        "source_type": "recording",
                        "source_id": int(recording["id"]),
                        "repeater_id": repeater_id,
                        "input_count": 1,
                        "audio_duration_seconds": _recording_duration_seconds(recording),
                        "elapsed_ms": int((time.monotonic() - usage_started) * 1000),
                        "reason": "remote_transcription_rate_limited",
                        "error": str(exc),
                        "metadata": {
                            "recording_start_time": recording.get("start_time"),
                            "repeater_name": recording.get("repeater_name"),
                        },
                    }
                )
            backoff_seconds = self._start_remote_backoff(exc)
            logger.warning(
                "Remote transcription rate limited for recording %s; leaving it pending for retry in %.0fs",
                recording["id"],
                backoff_seconds,
            )
            raise
        except Exception as exc:
            if usage_started is not None and not usage_recorded:
                self.db.add_api_usage_event(
                    {
                        "provider": "openai-compatible",
                        "call_type": "transcription",
                        "operation": "recording",
                        "model": self.config.transcription.remote_model,
                        "status": "error",
                        "source_type": "recording",
                        "source_id": int(recording["id"]),
                        "repeater_id": repeater_id,
                        "input_count": 1,
                        "audio_duration_seconds": _recording_duration_seconds(recording),
                        "elapsed_ms": int((time.monotonic() - usage_started) * 1000),
                        "reason": "remote_transcription",
                        "error": str(exc),
                        "metadata": {
                            "recording_start_time": recording.get("start_time"),
                            "repeater_name": recording.get("repeater_name"),
                        },
                    }
                )
            logger.exception("Transcription failed for recording %s", recording["id"])
            text = f"Transcription failed: {exc}"
            return self.db.add_transcript(
                recording_id=int(recording["id"]),
                text=text,
                original_text=text,
                confidence=None,
                low_confidence=True,
                backend=self.config.transcription.backend,
                segments=[],
                status="failed",
            )
