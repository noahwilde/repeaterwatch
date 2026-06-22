from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.config import AppConfig
from app.db import Database, parse_time

logger = logging.getLogger(__name__)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_vapid_keys() -> dict[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return {"public_key": b64url(public_key), "private_key": private_pem}


@dataclass
class KeywordMatch:
    rule: dict[str, Any]
    matched_text: str


AUTOMATED_TRAFFIC_SENTENCE_PATTERNS = (
    re.compile(r"^welcome to (?:the )?.*\brepeater$", re.IGNORECASE),
    re.compile(r"^this is (?:the )?.*\brepeater$", re.IGNORECASE),
    re.compile(r"^repeater id\b.*$", re.IGNORECASE),
    re.compile(r"^use tone\b.*$", re.IGNORECASE),
    re.compile(r"^tone\s+(?:\d|one|two|three|four|five|six|seven|eight|nine|zero).*$", re.IGNORECASE),
    re.compile(r"^.*amateur radio club repeater\b.*(?:use tone\b.*)?$", re.IGNORECASE),
    re.compile(r"^[A-Z]{1,2}\d[A-Z]{1,3}\s+repeater(?:\s+[A-Za-z][A-Za-z\s,.'-]*)?$", re.IGNORECASE),
)
NON_TRAFFIC_TEXTS = {
    "",
    "[static only]",
    "[inaudible]",
    "beep",
    "courtesy tone",
    "roger beep",
    "squelch tail",
    "tone",
}


def rule_matches_text(rule: dict[str, Any], text: str) -> str | None:
    keyword = str(rule["keyword"])
    flags = 0 if rule.get("case_sensitive") else re.IGNORECASE
    if rule.get("is_regex"):
        try:
            match = re.search(keyword, text, flags)
        except re.error:
            logger.warning("Invalid keyword regex ignored: %s", keyword)
            return None
        return match.group(0) if match else None
    haystack = text if rule.get("case_sensitive") else text.casefold()
    needle = keyword if rule.get("case_sensitive") else keyword.casefold()
    if needle in haystack:
        return keyword
    return None


def transcript_excerpt(text: str, limit: int = 180) -> str:
    value = " ".join(line.strip() for line in text.splitlines() if not line.strip().casefold().startswith("likely callsigns detected:"))
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}..."


def normalized_alert_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def suppressed_by_phrase(text: str, suppress_phrases: Iterable[str]) -> bool:
    normalized = normalized_alert_text(text)
    return any(normalized_alert_text(phrase) in normalized for phrase in suppress_phrases if phrase.strip())


def _transcript_sentences(text: str) -> list[str]:
    cleaned_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().casefold().startswith("likely callsigns detected:")
    ]
    cleaned = " ".join(cleaned_lines)
    parts = re.split(r"(?<=[.!?;])\s+|\n+", cleaned)
    return [part.strip(" \t\r\n,.:;!?") for part in parts if part.strip(" \t\r\n,.:;!?")]


def automated_transcript_sentence(sentence: str) -> bool:
    normalized = re.sub(r"\s+", " ", sentence).strip()
    casefolded = normalized.casefold()
    if casefolded in NON_TRAFFIC_TEXTS:
        return True
    return any(pattern.match(normalized) for pattern in AUTOMATED_TRAFFIC_SENTENCE_PATTERNS)


def non_automated_transcript_text(text: str, suppress_phrases: Iterable[str] = ()) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    casefolded = normalized.casefold()
    if suppressed_by_phrase(normalized, suppress_phrases):
        return False
    if casefolded in NON_TRAFFIC_TEXTS:
        return False
    if casefolded.startswith("[inaudible]"):
        return False
    if casefolded.startswith("transcription failed:") or casefolded.startswith("transcription is in manual/no-op mode"):
        return False
    sentences = _transcript_sentences(text)
    if not sentences:
        return False
    return any(not automated_transcript_sentence(sentence) for sentence in sentences)


class NotificationService:
    def __init__(self, db: Database, config: AppConfig):
        self.db = db
        self.config = config

    @property
    def public_key(self) -> str:
        value = os.getenv("REPEATERWATCH_VAPID_PUBLIC_KEY", "") or self.config.notifications.vapid_public_key
        return "".join(value.split())

    @property
    def private_key(self) -> str:
        value = os.getenv("REPEATERWATCH_VAPID_PRIVATE_KEY", "") or self.config.notifications.vapid_private_key
        return value.replace("\\n", "\n")

    def save_subscription(self, payload: dict[str, Any]) -> int:
        keys = payload.get("keys") or {}
        return self.db.upsert_push_subscription(
            endpoint=payload["endpoint"],
            p256dh=keys["p256dh"],
            auth=keys["auth"],
            user_agent=payload.get("user_agent", ""),
        )

    async def create_and_send_event(
        self,
        title: str,
        body: str,
        source_type: str,
        source_id: int,
        repeater_id: int | None = None,
        matched_text: str = "",
        url: str = "/",
    ) -> int:
        event_id = self.db.add_notification_event(
            {
                "rule_id": None,
                "repeater_id": repeater_id,
                "source_type": source_type,
                "source_id": source_id,
                "title": title,
                "body": body,
                "matched_text": matched_text,
            }
        )
        await self.send_event(event_id, title, body, url=url)
        return event_id

    async def send_event(self, event_id: int, title: str, body: str, url: str = "/") -> int:
        if not self.config.notifications.enabled:
            return 0
        if not self.private_key or not self.public_key:
            logger.warning("Web Push skipped because VAPID keys are not configured")
            return 0
        subscriptions = self.db.list_push_subscriptions()
        sent = 0
        payload = json.dumps({"title": title, "body": body, "url": url})
        for subscription in subscriptions:
            ok = await asyncio.to_thread(self._send_one, subscription, payload)
            if ok:
                sent += 1
        self.db.update_notification_sent_count(event_id, sent)
        return sent

    def _send_one(self, subscription: dict[str, Any], payload: str) -> bool:
        try:
            from py_vapid import Vapid
            from pywebpush import WebPushException, webpush
        except ImportError:
            logger.warning("pywebpush is not installed")
            return False

        subscription_info = {
            "endpoint": subscription["endpoint"],
            "keys": {
                "p256dh": subscription["p256dh"],
                "auth": subscription["auth"],
            },
        }
        try:
            vapid_key = Vapid.from_pem(self.private_key.encode("ascii"))
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_key,
                vapid_claims={"sub": self.config.notifications.subject},
                ttl=3600,
            )
            return True
        except WebPushException as exc:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            if status in (404, 410):
                self.db.disable_push_subscription(subscription["endpoint"])
            logger.warning("Web Push failed for subscription %s: %s", subscription["id"], exc)
            return False
        except Exception:
            logger.exception("Web Push failed for subscription %s before send", subscription["id"])
            return False


class ReceiverHealthNotifier:
    down_states = {"missing", "crashed", "error"}

    def __init__(self, notifications: NotificationService):
        self.notifications = notifications
        self._down_repeaters: set[int] = set()

    async def handle_status(self, repeater: dict[str, Any], state: str, message: str = "") -> int | None:
        repeater_id = int(repeater["id"])
        name = repeater.get("name", "Repeater")
        frequency = repeater.get("frequency_mhz")
        label = f"{name} {float(frequency):.6f} MHz" if frequency is not None else str(name)

        if state in self.down_states:
            if repeater_id in self._down_repeaters:
                return None
            self._down_repeaters.add(repeater_id)
            title = f"RepeaterWatch: {name} receiver down"
            body = f"{label} stopped receiving: {state}"
            if message:
                body = f"{body} - {message[:160]}"
            return await self.notifications.create_and_send_event(
                title=title,
                body=body,
                source_type="receiver_status",
                source_id=repeater_id,
                repeater_id=repeater_id,
                matched_text=state,
                url="/#logs",
            )

        if state == "running" and repeater_id in self._down_repeaters:
            self._down_repeaters.remove(repeater_id)
            title = f"RepeaterWatch: {name} receiver restored"
            body = f"{label} is receiving again."
            return await self.notifications.create_and_send_event(
                title=title,
                body=body,
                source_type="receiver_recovered",
                source_id=repeater_id,
                repeater_id=repeater_id,
                matched_text="running",
                url="/#monitor",
            )

        return None


class KeywordEngine:
    def __init__(self, db: Database, notifications: NotificationService):
        self.db = db
        self.notifications = notifications

    def matching_rules(
        self,
        source_type: str,
        repeater_id: int | None,
        text: str,
        now: datetime | None = None,
    ) -> list[KeywordMatch]:
        now = now or datetime.now(UTC)
        matches: list[KeywordMatch] = []
        for rule in self.db.list_keyword_rules(enabled=True):
            if source_type == "transcript" and not rule.get("notify_transcript"):
                continue
            if source_type == "summary" and not rule.get("notify_summary"):
                continue
            if rule.get("repeater_id") is not None and rule.get("repeater_id") != repeater_id:
                continue
            matched_text = rule_matches_text(rule, text)
            if not matched_text:
                continue
            if not self._cooldown_elapsed(rule, now):
                continue
            matches.append(KeywordMatch(rule=rule, matched_text=matched_text))
        return matches

    async def evaluate_and_notify(
        self,
        source_type: str,
        source_id: int,
        repeater_id: int | None,
        text: str,
        repeater_name: str = "Repeater",
    ) -> list[int]:
        event_ids: list[int] = []
        for match in self.matching_rules(source_type, repeater_id, text):
            title = f"RepeaterWatch: {match.rule['keyword']}"
            body = f"{repeater_name}: keyword matched in {source_type}"
            event_id = self.db.add_notification_event(
                {
                    "rule_id": match.rule["id"],
                    "repeater_id": repeater_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "title": title,
                    "body": body,
                    "matched_text": match.matched_text,
                }
            )
            await self.notifications.send_event(event_id, title, body)
            event_ids.append(event_id)
        return event_ids

    async def notify_traffic_transcript(
        self,
        source_id: int,
        repeater_id: int | None,
        text: str,
        repeater_name: str = "Repeater",
    ) -> int | None:
        if not self.db.traffic_alerts_enabled():
            return None
        if not non_automated_transcript_text(text, self.db.traffic_alert_suppress_phrases()):
            return None
        excerpt = transcript_excerpt(text)
        title = f"RepeaterWatch: traffic on {repeater_name}"
        body = f"{repeater_name}: {excerpt}" if excerpt else f"{repeater_name}: new transcript"
        return await self.notifications.create_and_send_event(
            title=title,
            body=body,
            source_type="traffic",
            source_id=source_id,
            repeater_id=repeater_id,
            matched_text=excerpt,
            url="/#review",
        )

    def _cooldown_elapsed(self, rule: dict[str, Any], now: datetime) -> bool:
        cooldown = int(rule.get("cooldown_minutes") or 0)
        if cooldown <= 0:
            return True
        last = self.db.last_notification_event(int(rule["id"]))
        if not last:
            return True
        last_time = parse_time(last["created_at"])
        return now - last_time >= timedelta(minutes=cooldown)
