from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.config import AppConfig
from app.db import Database
from app.notify.webpush import non_automated_transcript_text
from app.transcribe.whisper import detect_callsigns

logger = logging.getLogger(__name__)

SUMMARY_WINDOWS = {
    "quarter_hour": timedelta(minutes=15),
    "hour": timedelta(hours=1),
    "last_15_minutes": timedelta(minutes=15),
    "last_hour": timedelta(hours=1),
}
SUMMARY_WINDOW_ALIASES = {
    "last_15_minutes": "quarter_hour",
    "last_hour": "hour",
    "today": "day",
}
DAILY_ACTIVITY_PERIOD_GAP = timedelta(minutes=20)
DAILY_INDEX_EXCERPT_CHARS = 220


@dataclass
class SummarySelection:
    window_name: str
    start_time: datetime
    end_time: datetime
    transcripts: list[dict[str, Any]]
    local_timezone: tzinfo


ABSENT_CATEGORY_PATTERN = re.compile(
    r"(^|[,;]\s*)\b(?:no|not any)\s+[^.!?;]*\b("
    r"weather|emergenc(?:y|ies)|nets?|check[- ]?ins?|user traffic|road(?: conditions)?|"
    r"announcements?|other activity|other topics"
    r")\b[^.!?;]*",
    re.IGNORECASE,
)
ABSENT_SENTENCE_PATTERN = re.compile(
    r"^\s*(?:no|not any)\s+.*\b("
    r"weather|emergenc(?:y|ies)|nets?|check[- ]?ins?|user traffic|road(?: conditions)?|"
    r"announcements?|other activity|other topics"
    r")\b",
    re.IGNORECASE,
)


def remove_absent_category_claims(text: str) -> str:
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        cleaned_sentences: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if ABSENT_SENTENCE_PATTERN.search(sentence):
                continue
            cleaned = ABSENT_CATEGORY_PATTERN.sub("", sentence).strip(" ,;")
            if cleaned.strip(".!? "):
                cleaned_sentences.append(cleaned)
        if cleaned_sentences:
            cleaned_lines.append(" ".join(cleaned_sentences))
    return "\n".join(cleaned_lines).strip() or text


def system_local_timezone() -> tzinfo:
    return datetime.now(UTC).astimezone().tzinfo or UTC


def summary_timezone(value: str | None = "local") -> tzinfo:
    timezone_name = (value or "local").strip()
    if not timezone_name or timezone_name.casefold() in {"local", "system"}:
        return system_local_timezone()
    if timezone_name.casefold() == "utc":
        return UTC
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown summary timezone %s; using system local timezone", timezone_name)
        return system_local_timezone()


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=system_local_timezone()).astimezone(UTC)
    return value.astimezone(UTC)


def canonical_window_name(window_name: str) -> str:
    normalized = str(window_name or "quarter_hour").strip()
    return SUMMARY_WINDOW_ALIASES.get(normalized, normalized)


def window_bounds(
    window_name: str,
    now: datetime | None = None,
    local_tz: tzinfo | None = None,
) -> tuple[datetime, datetime]:
    window_name = canonical_window_name(window_name)
    now_utc = _as_utc(now)
    if window_name in SUMMARY_WINDOWS:
        return now_utc - SUMMARY_WINDOWS[window_name], now_utc
    if window_name == "day":
        timezone = local_tz or system_local_timezone()
        local_now = now_utc.astimezone(timezone)
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return local_start.astimezone(UTC), local_now.astimezone(UTC)
    raise ValueError(f"Unknown summary window: {window_name}")


def scheduled_window_bounds(
    window_name: str,
    now: datetime | None = None,
    local_tz: tzinfo | None = None,
) -> tuple[datetime, datetime]:
    window_name = canonical_window_name(window_name)
    now_utc = _as_utc(now)
    timezone = local_tz or system_local_timezone()
    local_now = now_utc.astimezone(timezone)
    if window_name == "quarter_hour":
        minute = local_now.minute - (local_now.minute % 15)
        local_end = local_now.replace(minute=minute, second=0, microsecond=0)
        local_start = local_end - timedelta(minutes=15)
    elif window_name == "hour":
        local_end = local_now.replace(minute=0, second=0, microsecond=0)
        local_start = local_end - timedelta(hours=1)
    elif window_name == "day":
        local_end = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        local_start = local_end - timedelta(days=1)
    else:
        raise ValueError(f"Unknown scheduled summary window: {window_name}")
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


def select_source_transcripts(
    db: Database,
    window_name: str,
    repeater_id: int | None = None,
    now: datetime | None = None,
    local_tz: tzinfo | None = None,
) -> SummarySelection:
    timezone = local_tz or system_local_timezone()
    start, end = window_bounds(window_name, now, timezone)
    return select_source_transcripts_between(db, window_name, start, end, repeater_id, timezone)


def select_source_transcripts_between(
    db: Database,
    window_name: str,
    start: datetime,
    end: datetime,
    repeater_id: int | None = None,
    local_tz: tzinfo | None = None,
) -> SummarySelection:
    timezone = local_tz or system_local_timezone()
    start_utc = _as_utc(start)
    end_utc = _as_utc(end)
    transcripts = db.transcripts_between(
        start_utc.isoformat(timespec="seconds"),
        end_utc.isoformat(timespec="seconds"),
        repeater_id=repeater_id,
    )
    return SummarySelection(canonical_window_name(window_name), start_utc, end_utc, transcripts, timezone)


def _parse_recording_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _prompt_datetime(value: Any, local_tz: tzinfo) -> str:
    parsed = _parse_recording_time(value)
    if parsed is None:
        return str(value or "unknown time")
    return parsed.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S %Z")


def _prompt_time(value: Any, local_tz: tzinfo) -> str:
    parsed = _parse_recording_time(value)
    if parsed is None:
        return str(value or "unknown time")
    return parsed.astimezone(local_tz).strftime("%H:%M:%S %Z")


def _compact_prompt_text(value: str, limit: int = DAILY_INDEX_EXCERPT_CHARS) -> str:
    compacted = re.sub(r"\s+", " ", value or "").strip()
    if len(compacted) <= limit:
        return compacted
    return compacted[: max(0, limit - 1)].rstrip() + "..."


def daily_activity_index(selection: SummarySelection) -> str:
    if canonical_window_name(selection.window_name) != "day" or not selection.transcripts:
        return ""

    lines = [
        "Daily Activity Index:",
        "Use this index as a coverage checklist before writing the summary. Every possible user-traffic period should be represented in the final summary.",
    ]
    previous_time: datetime | None = None
    period = 0
    total = len(selection.transcripts)
    for index, transcript in enumerate(selection.transcripts, start=1):
        current_time = _parse_recording_time(transcript.get("recording_start_time"))
        if previous_time is None or (
            current_time is not None
            and previous_time is not None
            and current_time - previous_time > DAILY_ACTIVITY_PERIOD_GAP
        ):
            period += 1
            lines.append(f"Activity period {period}:")
        previous_time = current_time or previous_time

        repeater_name = transcript.get("configured_repeater_name") or transcript.get("repeater_name", "Repeater")
        transcript_text = transcript.get("text", "")
        transcript_class = "possible user traffic" if non_automated_transcript_text(transcript_text) else "automated/system message only"
        lines.append(
            f"- [{index}/{total} {_prompt_time(transcript.get('recording_start_time'), selection.local_timezone)}] "
            f"{repeater_name}; {transcript_class}: {_compact_prompt_text(transcript_text)}"
        )
    return "\n".join(lines)


def build_summary_prompt(selection: SummarySelection) -> str:
    transcript_blocks = []
    for transcript in selection.transcripts:
        repeater_name = transcript.get("configured_repeater_name") or transcript.get("repeater_name", "Repeater")
        tone = transcript.get("repeater_tone") or "not configured"
        transcript_text = transcript.get("text", "")
        transcript_class = "possible user traffic" if non_automated_transcript_text(transcript_text) else "automated/system message only"
        metadata = [
            f"Time: {_prompt_datetime(transcript.get('recording_start_time'), selection.local_timezone)}",
            f"Name: {repeater_name}",
            f"RX Frequency: {transcript.get('frequency_mhz', '')} MHz",
            f"Tone: {tone}",
            f"Transcript Class: {transcript_class}",
        ]
        for label, field in (
            ("Location", "repeater_location"),
            ("Coverage Area", "repeater_coverage_area"),
            ("Type", "repeater_type"),
            ("Notes", "repeater_notes"),
        ):
            if transcript.get(field):
                metadata.append(f"{label}: {transcript[field]}")
        transcript_blocks.append(f"Repeater Metadata:\n" + "\n".join(metadata) + f"\nTranscript:\n{transcript_text}")
    joined = "\n\n".join(transcript_blocks)
    daily_guidance = ""
    coverage_index = daily_activity_index(selection)
    if canonical_window_name(selection.window_name) == "day":
        daily_guidance = (
            "This is a daily summary. Ensure complete chronological coverage of the entire day, not only the "
            "busiest stretch. First identify every distinct activity period, net, check-in sequence, announcement, "
            "and user-traffic cluster. If multiple nets or check-in sessions occur back to back, mention each one "
            "separately when the transcripts name different nets, net-control stations, topics, or purposes. Keep "
            "details for dense periods brief enough that quieter periods are still covered. "
        )
    coverage_section = f"{coverage_index}\n\n" if coverage_index else ""
    if canonical_window_name(selection.window_name) == "day":
        local_start = selection.start_time.astimezone(selection.local_timezone)
        local_end = selection.end_time.astimezone(selection.local_timezone)
        window_label = (
            f"day ({local_start:%Y-%m-%d %Z}, "
            f"{local_start:%H:%M} through {local_end:%H:%M} local time)"
        )
    else:
        window_label = selection.window_name
    return (
        "Summarize only analog FM amateur radio repeater traffic that is actually present in the transcripts. "
        "Do not list absent categories such as no weather, no emergencies, no nets, no check-ins, or no user "
        "traffic unless a transcript explicitly discusses the absence. Keep the summary concise. "
        f"{daily_guidance}"
        "Never include phrases such as no weather, no nets, no emergencies, no user traffic, or no announcements. "
        "Include only heard topics, stations or callsigns, nets/check-ins, weather/road/emergency mentions, repeated "
        "issues, and announcements. The Repeater Metadata block before each transcript is trusted receiver context. "
        "Use that context to preserve repeater attribution, recognize automated repeater IDs, and judge transcript quality. "
        "Transcript Class tells whether a transcript appears to be possible user traffic or automated/system message only. "
        "Do not describe automated/system message only transcripts as user traffic. Do not attribute automated repeater "
        "welcome messages, repeater IDs, locations, or tone instructions to a user callsign. If a transcript contains both "
        "user speech and automated repeater text, summarize them separately. "
        "If the expected repeater identity or a robotic ID is garbled, say the transcript quality is uncertain. "
        "Do not invent user callsigns or facts, and do not treat the repeater's own callsign as a calling station "
        "unless the transcript clearly says so.\n\n"
        f"Window: {window_label}\n"
        f"{coverage_section}"
        f"Transcripts:\n{joined}"
    )


class SummaryService:
    def __init__(self, db: Database, config: AppConfig):
        self.db = db
        self.config = config

    async def _summary_text_and_status(
        self,
        selection: SummarySelection,
        repeater_id: int | None = None,
        operation: str = "manual",
    ) -> tuple[str, str]:
        if len(selection.transcripts) < self.config.summary.min_transcripts:
            text = "Not enough traffic to summarize for this window."
            status = "not_enough_traffic"
            if self.config.summary.backend == "openai-compatible":
                self._record_summary_usage(
                    selection,
                    repeater_id=repeater_id,
                    operation=operation,
                    status="skipped",
                    reason="not_enough_traffic",
                )
        elif (
            self.config.summary.skip_automated_only
            and selection.transcripts
            and not any(non_automated_transcript_text(row.get("text", "")) for row in selection.transcripts)
        ):
            text = "Only automated/system repeater messages were heard in this window."
            status = "automated_only"
            if self.config.summary.backend == "openai-compatible":
                self._record_summary_usage(
                    selection,
                    repeater_id=repeater_id,
                    operation=operation,
                    status="skipped",
                    reason="automated_only",
                )
        elif self.config.summary.backend == "noop":
            text = self._noop_summary(selection)
            status = "completed"
        elif self.config.summary.backend == "openai-compatible":
            text = await self._openai_compatible_summary(selection, repeater_id, operation)
            status = "completed"
        elif self.config.summary.backend == "ollama":
            text = await self._ollama_summary(selection)
            status = "completed"
        else:
            raise ValueError(f"Unknown summary backend: {self.config.summary.backend}")
        return remove_absent_category_claims(text), status

    async def generate(
        self,
        window_name: str,
        repeater_id: int | None = None,
        now: datetime | None = None,
    ) -> int:
        local_tz = summary_timezone(self.config.summary.timezone)
        selection = select_source_transcripts(self.db, window_name, repeater_id, now, local_tz)
        return await self.generate_from_selection(selection, repeater_id, operation="manual")

    async def generate_from_selection(
        self,
        selection: SummarySelection,
        repeater_id: int | None = None,
        operation: str = "manual",
    ) -> int:
        text, status = await self._summary_text_and_status(selection, repeater_id, operation)
        return self.db.add_summary(
            {
                "window_name": selection.window_name,
                "repeater_id": repeater_id,
                "start_time": selection.start_time.isoformat(timespec="seconds"),
                "end_time": selection.end_time.isoformat(timespec="seconds"),
                "text": text,
                "model": self.config.summary.model,
                "prompt_version": self.config.summary.prompt_version,
                "source_transcript_ids": [row["id"] for row in selection.transcripts],
                "status": status,
            }
        )

    async def generate_ad_hoc(
        self,
        window_name: str,
        repeater_id: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        local_tz = summary_timezone(self.config.summary.timezone)
        selection = select_source_transcripts(self.db, window_name, repeater_id, now, local_tz)
        text, status = await self._summary_text_and_status(selection, repeater_id, operation="ad_hoc")
        return {
            "id": None,
            "ad_hoc": True,
            "window_name": selection.window_name,
            "repeater_id": repeater_id,
            "start_time": selection.start_time.isoformat(timespec="seconds"),
            "end_time": selection.end_time.isoformat(timespec="seconds"),
            "text": text,
            "model": self.config.summary.model,
            "prompt_version": self.config.summary.prompt_version,
            "source_transcript_ids": [row["id"] for row in selection.transcripts],
            "status": status,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }

    async def generate_scheduled(
        self,
        window_name: str,
        start: datetime,
        end: datetime,
        repeater_id: int | None = None,
        local_tz: tzinfo | None = None,
    ) -> int:
        timezone = local_tz or summary_timezone(self.config.summary.timezone)
        selection = select_source_transcripts_between(self.db, window_name, start, end, repeater_id, timezone)
        return await self.generate_from_selection(selection, repeater_id, operation="scheduled")

    def _noop_summary(self, selection: SummarySelection) -> str:
        texts = [row.get("text", "") for row in selection.transcripts]
        combined = "\n".join(texts)
        callsigns = detect_callsigns(combined)
        low_confidence_count = sum(1 for row in selection.transcripts if row.get("low_confidence"))
        lines = [
            f"Traffic heard in {len(selection.transcripts)} recording(s).",
            "AI summarization is disabled; this is an extractive local summary.",
        ]
        if callsigns:
            lines.append("Likely callsigns detected: " + ", ".join(callsigns))
        if low_confidence_count:
            lines.append(f"{low_confidence_count} transcript(s) were marked low confidence.")
        excerpt = " ".join(texts).strip()
        if excerpt:
            lines.append("Recent transcript excerpt: " + excerpt[:800])
        return "\n".join(lines)

    def _record_summary_usage(
        self,
        selection: SummarySelection,
        repeater_id: int | None,
        operation: str,
        status: str,
        reason: str,
        usage: dict[str, Any] | None = None,
        elapsed_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        usage = usage or {}
        self.db.add_api_usage_event(
            {
                "provider": "openai-compatible",
                "call_type": "summary",
                "operation": operation,
                "model": self.config.summary.model,
                "status": status,
                "source_type": "summary_window",
                "repeater_id": repeater_id,
                "window_name": selection.window_name,
                "input_count": len(selection.transcripts),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "elapsed_ms": elapsed_ms,
                "reason": reason,
                "error": error,
                "metadata": {
                    "start_time": selection.start_time.isoformat(timespec="seconds"),
                    "end_time": selection.end_time.isoformat(timespec="seconds"),
                    "source_transcript_ids": [row["id"] for row in selection.transcripts],
                },
            }
        )

    async def _openai_compatible_summary(
        self,
        selection: SummarySelection,
        repeater_id: int | None,
        operation: str,
    ) -> str:
        api_key = os.getenv(self.config.summary.api_key_env, "")
        if not api_key:
            raise RuntimeError(f"{self.config.summary.api_key_env} is not set")
        url = f"{self.config.summary.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.config.summary.model,
            "messages": [
                {"role": "system", "content": "You summarize radio traffic conservatively."},
                {"role": "user", "content": build_summary_prompt(selection)},
            ],
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            self._record_summary_usage(
                selection,
                repeater_id=repeater_id,
                operation=operation,
                status="success",
                reason="remote_summary",
                usage=data.get("usage") or {},
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            return content
        except Exception as exc:
            self._record_summary_usage(
                selection,
                repeater_id=repeater_id,
                operation=operation,
                status="error",
                reason="remote_summary",
                elapsed_ms=int((time.monotonic() - started) * 1000),
                error=str(exc),
            )
            raise

    async def _ollama_summary(self, selection: SummarySelection) -> str:
        url = f"{self.config.summary.base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.config.summary.model,
            "stream": False,
            "messages": [{"role": "user", "content": build_summary_prompt(selection)}],
            "options": {"temperature": 0.1},
        }
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "").strip()


class SummaryWorker:
    def __init__(self, db: Database, config: AppConfig, keyword_engine: Any | None = None):
        self.db = db
        self.config = config
        self.service = SummaryService(db, config)
        self.keyword_engine = keyword_engine
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                await self.generate_rolling()
            except Exception:
                logger.exception("Summary worker pass failed")
            await asyncio.sleep(self.config.summary.poll_seconds)

    def stop(self) -> None:
        self.stop_event.set()

    async def generate_rolling(self, now: datetime | None = None) -> list[int]:
        summary_ids: list[int] = []
        repeaters = self.db.list_repeaters()
        local_tz = summary_timezone(self.config.summary.timezone)
        bounds_now = _as_utc(now) - timedelta(seconds=self.config.summary.schedule_delay_seconds)
        windows = list(dict.fromkeys(self.config.summary.scheduled_windows))
        targets: list[tuple[str, int | None]] = [(window_name, None) for window_name in windows]
        if self.config.summary.per_repeater_scheduled:
            for repeater in repeaters:
                targets.extend((window_name, int(repeater["id"])) for window_name in windows)
        for window_name, repeater_id in targets:
            start, end = scheduled_window_bounds(window_name, bounds_now, local_tz)
            selection = select_source_transcripts_between(self.db, window_name, start, end, repeater_id, local_tz)
            source_ids = [row["id"] for row in selection.transcripts]
            if len(source_ids) < self.config.summary.min_transcripts:
                continue
            if self._period_summary_matches(window_name, repeater_id, start, end, source_ids):
                continue
            summary_id = await self.service.generate_from_selection(selection, repeater_id, operation="scheduled")
            summary_ids.append(summary_id)
            summary = self.db.query_one("SELECT * FROM summaries WHERE id = ?", (summary_id,))
            if summary and summary["status"] == "completed" and self.keyword_engine:
                repeater_name = "All repeaters"
                if repeater_id is not None:
                    repeater = self.db.get_repeater(repeater_id)
                    repeater_name = repeater["name"] if repeater else "Repeater"
                await self.keyword_engine.evaluate_and_notify(
                    source_type="summary",
                    source_id=summary_id,
                    repeater_id=repeater_id,
                    text=summary["text"],
                    repeater_name=repeater_name,
                )
        return summary_ids

    def _period_summary(self, window_name: str, repeater_id: int | None, start: datetime, end: datetime) -> dict[str, Any] | None:
        window_name = canonical_window_name(window_name)
        start_text = _as_utc(start).isoformat(timespec="seconds")
        end_text = _as_utc(end).isoformat(timespec="seconds")
        if repeater_id is None:
            return self.db.query_one(
                """
                SELECT * FROM summaries
                WHERE window_name = ? AND repeater_id IS NULL AND start_time = ? AND end_time = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (window_name, start_text, end_text),
            )
        return self.db.query_one(
            """
            SELECT * FROM summaries
            WHERE window_name = ? AND repeater_id = ? AND start_time = ? AND end_time = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (window_name, repeater_id, start_text, end_text),
        )

    def _period_summary_matches(
        self,
        window_name: str,
        repeater_id: int | None,
        start: datetime,
        end: datetime,
        source_ids: list[int],
    ) -> bool:
        row = self._period_summary(window_name, repeater_id, start, end)
        if not row:
            return False
        try:
            latest_source_ids = list(json.loads(row["source_transcript_ids"]))
        except json.JSONDecodeError:
            latest_source_ids = []
        if (
            latest_source_ids == source_ids
            and row.get("model") == self.config.summary.model
            and row.get("prompt_version") == self.config.summary.prompt_version
            and (
                row.get("status") == "completed"
                or (
                    row.get("status") == "automated_only"
                    and self.config.summary.skip_automated_only
                )
                or row.get("status") == "not_enough_traffic"
            )
        ):
            return True
        self.db.delete_summary(int(row["id"]))
        return False
