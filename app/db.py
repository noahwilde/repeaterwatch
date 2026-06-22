from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from app.config import RepeaterConfig


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def migrate(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS repeaters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                frequency_mhz REAL NOT NULL,
                transmit_frequency_mhz REAL,
                offset_mhz REAL,
                tone TEXT,
                mode TEXT NOT NULL DEFAULT 'NFM',
                squelch_level INTEGER NOT NULL DEFAULT 50,
                sample_rate INTEGER NOT NULL DEFAULT 24000,
                gain TEXT NOT NULL DEFAULT 'auto',
                ppm INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                description TEXT,
                location TEXT,
                coverage_area TEXT,
                repeater_type TEXT,
                notes TEXT,
                keyword_list TEXT NOT NULL DEFAULT '[]',
                notification_settings TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repeater_id INTEGER,
                frequency_mhz REAL NOT NULL,
                repeater_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_seconds REAL,
                level_proxy REAL,
                audio_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'completed',
                error TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recording_id INTEGER NOT NULL UNIQUE,
                text TEXT NOT NULL DEFAULT '',
                original_text TEXT NOT NULL DEFAULT '',
                corrected_text TEXT,
                confidence REAL,
                low_confidence INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                backend TEXT NOT NULL DEFAULT 'noop',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(recording_id) REFERENCES recordings(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS transcript_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcript_id INTEGER NOT NULL,
                start_seconds REAL NOT NULL,
                end_seconds REAL NOT NULL,
                text TEXT NOT NULL,
                confidence REAL,
                FOREIGN KEY(transcript_id) REFERENCES transcripts(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                window_name TEXT NOT NULL,
                repeater_id INTEGER,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                text TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                source_transcript_ids TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS keyword_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                is_regex INTEGER NOT NULL DEFAULT 0,
                case_sensitive INTEGER NOT NULL DEFAULT 0,
                repeater_id INTEGER,
                notify_transcript INTEGER NOT NULL DEFAULT 1,
                notify_summary INTEGER NOT NULL DEFAULT 0,
                cooldown_minutes INTEGER NOT NULL DEFAULT 10,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notification_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER,
                repeater_id INTEGER,
                source_type TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                matched_text TEXT NOT NULL,
                sent_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(rule_id) REFERENCES keyword_rules(id) ON DELETE SET NULL,
                FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL UNIQUE,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                user_agent TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS receiver_status (
                repeater_id INTEGER PRIMARY KEY,
                state TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                pid INTEGER,
                started_at TEXT,
                updated_at TEXT NOT NULL,
                restart_count INTEGER NOT NULL DEFAULT 0,
                level_proxy REAL,
                FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS api_usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                provider TEXT NOT NULL,
                call_type TEXT NOT NULL,
                operation TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                source_type TEXT,
                source_id INTEGER,
                repeater_id INTEGER,
                window_name TEXT,
                input_count INTEGER,
                audio_duration_seconds REAL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                elapsed_ms INTEGER,
                reason TEXT,
                error TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE SET NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_recordings_created_at ON recordings(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings(status)",
            "CREATE INDEX IF NOT EXISTS idx_transcripts_status ON transcripts(status)",
            "CREATE INDEX IF NOT EXISTS idx_summaries_created_at ON summaries(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_notification_events_rule_created ON notification_events(rule_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_api_usage_events_created ON api_usage_events(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_api_usage_events_type_created ON api_usage_events(call_type, created_at)",
        ]
        with self._lock:
            for statement in statements:
                self._conn.execute(statement)
            self._ensure_repeater_columns()
            self._conn.commit()

    def _ensure_repeater_columns(self) -> None:
        existing = {row["name"] for row in self._conn.execute("PRAGMA table_info(repeaters)").fetchall()}
        columns = {
            "transmit_frequency_mhz": "REAL",
            "description": "TEXT",
            "location": "TEXT",
            "coverage_area": "TEXT",
            "repeater_type": "TEXT",
            "notes": "TEXT",
            "keyword_list": "TEXT NOT NULL DEFAULT '[]'",
            "notification_settings": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in columns.items():
            if name not in existing:
                self._conn.execute(f"ALTER TABLE repeaters ADD COLUMN {name} {definition}")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cursor

    def query_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None

    def get_app_setting(self, key: str, default: str = "") -> str:
        row = self.query_one("SELECT value FROM app_settings WHERE key = ?", (key,))
        return str(row["value"]) if row else default

    def set_app_setting(self, key: str, value: str) -> None:
        self.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def traffic_alerts_enabled(self) -> bool:
        return self.get_app_setting("traffic_alerts_enabled", "0").strip().casefold() in {"1", "true", "yes", "on"}

    def set_traffic_alerts_enabled(self, enabled: bool) -> None:
        self.set_app_setting("traffic_alerts_enabled", "1" if enabled else "0")

    def traffic_alert_suppress_phrases_text(self) -> str:
        return self.get_app_setting("traffic_alert_suppress_phrases", "")

    def traffic_alert_suppress_phrases(self) -> list[str]:
        return [
            line.strip()
            for line in self.traffic_alert_suppress_phrases_text().splitlines()
            if line.strip()
        ]

    def set_traffic_alert_suppress_phrases(self, value: str) -> None:
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        self.set_app_setting("traffic_alert_suppress_phrases", "\n".join(lines))

    def seed_repeaters(self, repeaters: list[RepeaterConfig]) -> None:
        if not repeaters:
            return
        for repeater in repeaters:
            existing = self.query_one("SELECT id FROM repeaters WHERE name = ?", (repeater.name,))
            if existing:
                continue
            self.create_repeater(repeater.model_dump())

    def list_repeaters(self, enabled: bool | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM repeaters"
        params: list[Any] = []
        if enabled is not None:
            sql += " WHERE enabled = ?"
            params.append(1 if enabled else 0)
        sql += " ORDER BY name"
        return [self._normalize_repeater(row) for row in self.query_all(sql, params)]

    def get_repeater(self, repeater_id: int) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM repeaters WHERE id = ?", (repeater_id,))
        return self._normalize_repeater(row) if row else None

    def create_repeater(self, data: dict[str, Any]) -> int:
        now = utc_now()
        cursor = self.execute(
            """
            INSERT INTO repeaters
            (name, frequency_mhz, transmit_frequency_mhz, offset_mhz, tone, mode, squelch_level,
             sample_rate, gain, ppm, enabled, description, location, coverage_area, repeater_type,
             notes, keyword_list, notification_settings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"],
                data["frequency_mhz"],
                data.get("transmit_frequency_mhz"),
                data.get("offset_mhz"),
                data.get("tone"),
                data.get("mode", "NFM"),
                data.get("squelch_level", 50),
                data.get("sample_rate", 24_000),
                data.get("gain", "auto"),
                data.get("ppm", 0),
                1 if data.get("enabled", True) else 0,
                data.get("description"),
                data.get("location"),
                data.get("coverage_area"),
                data.get("repeater_type"),
                data.get("notes"),
                json.dumps(data.get("keyword_list", [])),
                json.dumps(data.get("notification_settings", {})),
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def update_repeater(self, repeater_id: int, data: dict[str, Any]) -> None:
        self.execute(
            """
            UPDATE repeaters
            SET name = ?, frequency_mhz = ?, transmit_frequency_mhz = ?, offset_mhz = ?, tone = ?, mode = ?,
                squelch_level = ?, sample_rate = ?, gain = ?, ppm = ?, enabled = ?,
                description = ?, location = ?, coverage_area = ?, repeater_type = ?, notes = ?,
                keyword_list = ?, notification_settings = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["name"],
                data["frequency_mhz"],
                data.get("transmit_frequency_mhz"),
                data.get("offset_mhz"),
                data.get("tone"),
                data.get("mode", "NFM"),
                data.get("squelch_level", 50),
                data.get("sample_rate", 24_000),
                data.get("gain", "auto"),
                data.get("ppm", 0),
                1 if data.get("enabled", True) else 0,
                data.get("description"),
                data.get("location"),
                data.get("coverage_area"),
                data.get("repeater_type"),
                data.get("notes"),
                json.dumps(data.get("keyword_list", [])),
                json.dumps(data.get("notification_settings", {})),
                utc_now(),
                repeater_id,
            ),
        )

    def delete_repeater(self, repeater_id: int) -> None:
        self.execute("DELETE FROM repeaters WHERE id = ?", (repeater_id,))

    def add_recording(self, data: dict[str, Any]) -> int:
        cursor = self.execute(
            """
            INSERT INTO recordings
            (repeater_id, frequency_mhz, repeater_name, start_time, end_time, duration_seconds,
             level_proxy, audio_path, status, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("repeater_id"),
                data["frequency_mhz"],
                data["repeater_name"],
                data["start_time"],
                data.get("end_time"),
                data.get("duration_seconds"),
                data.get("level_proxy"),
                data["audio_path"],
                data.get("status", "completed"),
                data.get("error"),
                data.get("created_at", utc_now()),
            ),
        )
        return int(cursor.lastrowid)

    def list_recordings(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.query_all(
            "SELECT * FROM recordings ORDER BY start_time DESC LIMIT ?",
            (limit,),
        )

    def list_static_only_recordings(self) -> list[dict[str, Any]]:
        return self.query_all(
            """
            SELECT r.* FROM recordings r
            JOIN transcripts t ON t.recording_id = r.id
            WHERE lower(trim(t.text)) = '[static only]'
            ORDER BY r.start_time DESC
            """
        )

    def recording_activity(
        self,
        now: datetime | None = None,
        hours: int = 24,
        bucket_minutes: int = 15,
    ) -> dict[str, Any]:
        end_time = now or datetime.now(UTC)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=UTC)
        else:
            end_time = end_time.astimezone(UTC)
        end_time = end_time.replace(microsecond=0)

        bucket_seconds = max(60, int(bucket_minutes) * 60)
        bucket_count = max(1, int((max(1, hours) * 3600) / bucket_seconds))
        start_time = end_time - timedelta(seconds=bucket_count * bucket_seconds)

        buckets = [
            {
                "start_time": (start_time + timedelta(seconds=index * bucket_seconds)).isoformat(timespec="seconds"),
                "end_time": (start_time + timedelta(seconds=(index + 1) * bucket_seconds)).isoformat(timespec="seconds"),
            }
            for index in range(bucket_count)
        ]

        def empty_repeater(row: dict[str, Any]) -> dict[str, Any]:
            return {
                "repeater_id": row.get("id") or row.get("repeater_id"),
                "name": row["name"],
                "frequency_mhz": row.get("frequency_mhz"),
                "total_count": 0,
                "total_duration_seconds": 0.0,
                "buckets": [{"count": 0, "duration_seconds": 0.0} for _ in range(bucket_count)],
            }

        repeaters: list[dict[str, Any]] = []
        repeater_by_key: dict[str, dict[str, Any]] = {}
        for repeater in self.list_repeaters():
            key = str(repeater["id"])
            activity = empty_repeater(repeater)
            repeaters.append(activity)
            repeater_by_key[key] = activity

        rows = self.query_all(
            """
            SELECT repeater_id, frequency_mhz, repeater_name, start_time, duration_seconds
            FROM recordings
            WHERE start_time >= ? AND start_time <= ? AND status != 'error'
            ORDER BY start_time ASC
            """,
            (start_time.isoformat(timespec="seconds"), end_time.isoformat(timespec="seconds")),
        )

        for row in rows:
            try:
                recording_start = parse_time(row["start_time"])
            except ValueError:
                continue
            if recording_start.tzinfo is None:
                recording_start = recording_start.replace(tzinfo=UTC)
            else:
                recording_start = recording_start.astimezone(UTC)
            if recording_start < start_time or recording_start > end_time:
                continue

            bucket_index = int((recording_start - start_time).total_seconds() // bucket_seconds)
            if bucket_index >= bucket_count:
                bucket_index = bucket_count - 1

            repeater_key = str(row["repeater_id"]) if row.get("repeater_id") is not None else f"name:{row['repeater_name']}"
            if repeater_key not in repeater_by_key:
                repeater = empty_repeater(
                    {
                        "repeater_id": row.get("repeater_id"),
                        "name": row["repeater_name"],
                        "frequency_mhz": row.get("frequency_mhz"),
                    }
                )
                repeaters.append(repeater)
                repeater_by_key[repeater_key] = repeater

            duration = max(0.0, float(row.get("duration_seconds") or 0.0))
            repeater = repeater_by_key[repeater_key]
            repeater["total_count"] += 1
            repeater["total_duration_seconds"] += duration
            repeater["buckets"][bucket_index]["count"] += 1
            repeater["buckets"][bucket_index]["duration_seconds"] += duration

        return {
            "start_time": start_time.isoformat(timespec="seconds"),
            "end_time": end_time.isoformat(timespec="seconds"),
            "bucket_minutes": int(bucket_seconds / 60),
            "buckets": buckets,
            "repeaters": repeaters,
        }

    def get_recording(self, recording_id: int) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM recordings WHERE id = ?", (recording_id,))

    def delete_recording(self, recording_id: int) -> None:
        self.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))

    def pending_recordings_for_transcription(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.query_all(
            """
            SELECT r.* FROM recordings r
            LEFT JOIN transcripts t ON t.recording_id = r.id
            WHERE r.status = 'completed' AND t.id IS NULL
            ORDER BY r.start_time ASC
            LIMIT ?
            """,
            (limit,),
        )

    def add_transcript(
        self,
        recording_id: int,
        text: str,
        original_text: str,
        confidence: float | None,
        low_confidence: bool,
        backend: str,
        segments: list[dict[str, Any]],
        status: str = "completed",
    ) -> int:
        now = utc_now()
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO transcripts
                (recording_id, text, original_text, confidence, low_confidence, status, backend, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(recording_id) DO UPDATE SET
                    text = excluded.text,
                    original_text = excluded.original_text,
                    confidence = excluded.confidence,
                    low_confidence = excluded.low_confidence,
                    status = excluded.status,
                    backend = excluded.backend,
                    updated_at = excluded.updated_at
                """,
                (
                    recording_id,
                    text,
                    original_text,
                    confidence,
                    1 if low_confidence else 0,
                    status,
                    backend,
                    now,
                    now,
                ),
            )
            transcript = self._conn.execute(
                "SELECT id FROM transcripts WHERE recording_id = ?", (recording_id,)
            ).fetchone()
            transcript_id = int(transcript["id"])
            self._conn.execute("DELETE FROM transcript_segments WHERE transcript_id = ?", (transcript_id,))
            for segment in segments:
                self._conn.execute(
                    """
                    INSERT INTO transcript_segments
                    (transcript_id, start_seconds, end_seconds, text, confidence)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        transcript_id,
                        segment["start_seconds"],
                        segment["end_seconds"],
                        segment["text"],
                        segment.get("confidence"),
                    ),
                )
            self._conn.commit()
            return transcript_id

    def list_transcripts(self, limit: int = 50) -> list[dict[str, Any]]:
        return [self._normalize_bool(row, ["low_confidence"]) for row in self.query_all(
            """
            SELECT t.*, r.repeater_name, r.frequency_mhz, r.start_time
            FROM transcripts t
            JOIN recordings r ON r.id = t.recording_id
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )]

    def get_transcript_for_recording(self, recording_id: int) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM transcripts WHERE recording_id = ?", (recording_id,))
        return self._normalize_bool(row, ["low_confidence"]) if row else None

    def update_transcript_correction(self, transcript_id: int, corrected_text: str) -> None:
        self.execute(
            "UPDATE transcripts SET corrected_text = ?, text = ?, updated_at = ? WHERE id = ?",
            (corrected_text, corrected_text, utc_now(), transcript_id),
        )

    def transcript_segments(self, transcript_id: int) -> list[dict[str, Any]]:
        return self.query_all(
            "SELECT * FROM transcript_segments WHERE transcript_id = ? ORDER BY start_seconds",
            (transcript_id,),
        )

    def transcripts_between(
        self,
        start_time: str,
        end_time: str,
        repeater_id: int | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [start_time, end_time]
        repeater_clause = ""
        if repeater_id is not None:
            repeater_clause = "AND r.repeater_id = ?"
            params.append(repeater_id)
        return [self._normalize_bool(row, ["low_confidence"]) for row in self.query_all(
            f"""
            SELECT
              t.*,
              r.repeater_id,
              r.repeater_name,
              r.frequency_mhz,
              r.start_time AS recording_start_time,
              repeaters.name AS configured_repeater_name,
              repeaters.tone AS repeater_tone,
              repeaters.location AS repeater_location,
              repeaters.coverage_area AS repeater_coverage_area,
              repeaters.repeater_type AS repeater_type,
              repeaters.notes AS repeater_notes
            FROM transcripts t
            JOIN recordings r ON r.id = t.recording_id
            LEFT JOIN repeaters ON repeaters.id = r.repeater_id
            WHERE r.start_time >= ? AND r.start_time <= ? {repeater_clause}
              AND t.status = 'completed'
            ORDER BY r.start_time ASC
            """,
            params,
        )]

    def add_summary(self, data: dict[str, Any]) -> int:
        cursor = self.execute(
            """
            INSERT INTO summaries
            (window_name, repeater_id, start_time, end_time, text, model, prompt_version,
             source_transcript_ids, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["window_name"],
                data.get("repeater_id"),
                data["start_time"],
                data["end_time"],
                data["text"],
                data["model"],
                data["prompt_version"],
                json.dumps(data.get("source_transcript_ids", [])),
                data.get("status", "completed"),
                data.get("created_at", utc_now()),
            ),
        )
        return int(cursor.lastrowid)

    def list_summaries(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.query_all(
            "SELECT * FROM summaries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    def get_summary(self, summary_id: int) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM summaries WHERE id = ?", (summary_id,))

    def delete_summary(self, summary_id: int) -> None:
        self.execute("DELETE FROM summaries WHERE id = ?", (summary_id,))

    def clear_summaries(self) -> int:
        cursor = self.execute("DELETE FROM summaries")
        return int(cursor.rowcount)

    def create_keyword_rule(self, data: dict[str, Any]) -> int:
        now = utc_now()
        cursor = self.execute(
            """
            INSERT INTO keyword_rules
            (keyword, is_regex, case_sensitive, repeater_id, notify_transcript, notify_summary,
             cooldown_minutes, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["keyword"],
                1 if data.get("is_regex", False) else 0,
                1 if data.get("case_sensitive", False) else 0,
                data.get("repeater_id"),
                1 if data.get("notify_transcript", True) else 0,
                1 if data.get("notify_summary", False) else 0,
                data.get("cooldown_minutes", 10),
                1 if data.get("enabled", True) else 0,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def list_keyword_rules(self, enabled: bool | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM keyword_rules"
        params: list[Any] = []
        if enabled is not None:
            sql += " WHERE enabled = ?"
            params.append(1 if enabled else 0)
        sql += " ORDER BY id DESC"
        return [
            self._normalize_bool(
                row,
                ["is_regex", "case_sensitive", "notify_transcript", "notify_summary", "enabled"],
            )
            for row in self.query_all(sql, params)
        ]

    def update_keyword_rule(self, rule_id: int, data: dict[str, Any]) -> None:
        self.execute(
            """
            UPDATE keyword_rules
            SET keyword = ?, is_regex = ?, case_sensitive = ?, repeater_id = ?,
                notify_transcript = ?, notify_summary = ?, cooldown_minutes = ?,
                enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                data["keyword"],
                1 if data.get("is_regex", False) else 0,
                1 if data.get("case_sensitive", False) else 0,
                data.get("repeater_id"),
                1 if data.get("notify_transcript", True) else 0,
                1 if data.get("notify_summary", False) else 0,
                data.get("cooldown_minutes", 10),
                1 if data.get("enabled", True) else 0,
                utc_now(),
                rule_id,
            ),
        )

    def delete_keyword_rule(self, rule_id: int) -> None:
        self.execute("DELETE FROM keyword_rules WHERE id = ?", (rule_id,))

    def last_notification_event(self, rule_id: int) -> dict[str, Any] | None:
        return self.query_one(
            "SELECT * FROM notification_events WHERE rule_id = ? ORDER BY created_at DESC LIMIT 1",
            (rule_id,),
        )

    def add_notification_event(self, data: dict[str, Any]) -> int:
        cursor = self.execute(
            """
            INSERT INTO notification_events
            (rule_id, repeater_id, source_type, source_id, title, body, matched_text, sent_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("rule_id"),
                data.get("repeater_id"),
                data["source_type"],
                data["source_id"],
                data["title"],
                data["body"],
                data["matched_text"],
                data.get("sent_count", 0),
                data.get("created_at", utc_now()),
            ),
        )
        return int(cursor.lastrowid)

    def update_notification_sent_count(self, event_id: int, sent_count: int) -> None:
        self.execute("UPDATE notification_events SET sent_count = ? WHERE id = ?", (sent_count, event_id))

    def list_notification_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.query_all(
            "SELECT * FROM notification_events ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        )

    def get_notification_event(self, event_id: int) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM notification_events WHERE id = ?", (event_id,))

    def delete_notification_event(self, event_id: int) -> None:
        self.execute("DELETE FROM notification_events WHERE id = ?", (event_id,))

    def clear_notification_events(self) -> int:
        cursor = self.execute("DELETE FROM notification_events")
        return int(cursor.rowcount)

    def add_api_usage_event(self, data: dict[str, Any]) -> int:
        metadata = data.get("metadata", {})
        cursor = self.execute(
            """
            INSERT INTO api_usage_events
            (created_at, provider, call_type, operation, model, status, source_type, source_id,
             repeater_id, window_name, input_count, audio_duration_seconds, prompt_tokens,
             completion_tokens, total_tokens, elapsed_ms, reason, error, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("created_at", utc_now()),
                data.get("provider", "openai-compatible"),
                data["call_type"],
                data.get("operation", ""),
                data.get("model", ""),
                data.get("status", "success"),
                data.get("source_type"),
                data.get("source_id"),
                data.get("repeater_id"),
                data.get("window_name"),
                data.get("input_count"),
                data.get("audio_duration_seconds"),
                data.get("prompt_tokens"),
                data.get("completion_tokens"),
                data.get("total_tokens"),
                data.get("elapsed_ms"),
                data.get("reason"),
                data.get("error"),
                json.dumps(metadata if isinstance(metadata, dict) else {}),
            ),
        )
        return int(cursor.lastrowid)

    def list_api_usage_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return [self._normalize_api_usage_event(row) for row in self.query_all(
            """
            SELECT e.*, r.name AS repeater_name
            FROM api_usage_events e
            LEFT JOIN repeaters r ON r.id = e.repeater_id
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT ?
            """,
            (limit,),
        )]

    def api_usage_report(
        self,
        now: datetime | None = None,
        hours: int = 24,
        bucket_minutes: int = 60,
        event_limit: int = 50,
    ) -> dict[str, Any]:
        end_time = now or datetime.now(UTC)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=UTC)
        else:
            end_time = end_time.astimezone(UTC)
        end_time = end_time.replace(microsecond=0)

        bucket_seconds = max(60, int(bucket_minutes) * 60)
        bucket_count = max(1, int((max(1, hours) * 3600) / bucket_seconds))
        start_time = end_time - timedelta(seconds=bucket_count * bucket_seconds)
        buckets = [
            {
                "start_time": (start_time + timedelta(seconds=index * bucket_seconds)).isoformat(timespec="seconds"),
                "end_time": (start_time + timedelta(seconds=(index + 1) * bucket_seconds)).isoformat(timespec="seconds"),
            }
            for index in range(bucket_count)
        ]

        rows = [self._normalize_api_usage_event(row) for row in self.query_all(
            """
            SELECT e.*, r.name AS repeater_name
            FROM api_usage_events e
            LEFT JOIN repeaters r ON r.id = e.repeater_id
            WHERE e.created_at >= ? AND e.created_at <= ?
            ORDER BY e.created_at ASC, e.id ASC
            """,
            (start_time.isoformat(timespec="seconds"), end_time.isoformat(timespec="seconds")),
        )]

        totals = {
            "events": 0,
            "remote_calls": 0,
            "success": 0,
            "skipped": 0,
            "errors": 0,
            "audio_duration_seconds": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "token_events": 0,
        }
        series_by_type: dict[str, dict[str, Any]] = {}
        models: dict[tuple[str, str], dict[str, Any]] = {}
        reasons: dict[tuple[str, str, str], dict[str, Any]] = {}

        def empty_bucket() -> dict[str, Any]:
            return {
                "events": 0,
                "remote_calls": 0,
                "success": 0,
                "skipped": 0,
                "errors": 0,
                "audio_duration_seconds": 0.0,
                "total_tokens": 0,
            }

        def series_for(call_type: str) -> dict[str, Any]:
            if call_type not in series_by_type:
                series_by_type[call_type] = {
                    "call_type": call_type,
                    "events": 0,
                    "remote_calls": 0,
                    "success": 0,
                    "skipped": 0,
                    "errors": 0,
                    "audio_duration_seconds": 0.0,
                    "total_tokens": 0,
                    "buckets": [empty_bucket() for _ in range(bucket_count)],
                }
            return series_by_type[call_type]

        for row in rows:
            totals["events"] += 1
            call_type = str(row.get("call_type") or "unknown")
            status = str(row.get("status") or "unknown")
            remote_call = status != "skipped"
            success = status == "success"
            skipped = status == "skipped"
            error = status == "error"
            audio_seconds = float(row.get("audio_duration_seconds") or 0.0) if remote_call else 0.0
            prompt_tokens = int(row.get("prompt_tokens") or 0)
            completion_tokens = int(row.get("completion_tokens") or 0)
            total_tokens = int(row.get("total_tokens") or 0)
            has_tokens = any(row.get(field) is not None for field in ("prompt_tokens", "completion_tokens", "total_tokens"))

            if remote_call:
                totals["remote_calls"] += 1
            if success:
                totals["success"] += 1
            if skipped:
                totals["skipped"] += 1
            if error:
                totals["errors"] += 1
            totals["audio_duration_seconds"] += audio_seconds
            totals["prompt_tokens"] += prompt_tokens
            totals["completion_tokens"] += completion_tokens
            totals["total_tokens"] += total_tokens
            if has_tokens:
                totals["token_events"] += 1

            try:
                created_at = parse_time(str(row["created_at"]))
            except (KeyError, ValueError):
                created_at = start_time
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            else:
                created_at = created_at.astimezone(UTC)
            bucket_index = int((created_at - start_time).total_seconds() // bucket_seconds)
            bucket_index = min(max(0, bucket_index), bucket_count - 1)

            series = series_for(call_type)
            series["events"] += 1
            if remote_call:
                series["remote_calls"] += 1
            if success:
                series["success"] += 1
            if skipped:
                series["skipped"] += 1
            if error:
                series["errors"] += 1
            series["audio_duration_seconds"] += audio_seconds
            series["total_tokens"] += total_tokens

            bucket = series["buckets"][bucket_index]
            bucket["events"] += 1
            if remote_call:
                bucket["remote_calls"] += 1
            if success:
                bucket["success"] += 1
            if skipped:
                bucket["skipped"] += 1
            if error:
                bucket["errors"] += 1
            bucket["audio_duration_seconds"] += audio_seconds
            bucket["total_tokens"] += total_tokens

            if remote_call:
                model_key = (call_type, str(row.get("model") or "unknown"))
                model_row = models.setdefault(
                    model_key,
                    {
                        "call_type": call_type,
                        "model": model_key[1],
                        "remote_calls": 0,
                        "success": 0,
                        "errors": 0,
                        "audio_duration_seconds": 0.0,
                        "total_tokens": 0,
                    },
                )
                model_row["remote_calls"] += 1
                if success:
                    model_row["success"] += 1
                if error:
                    model_row["errors"] += 1
                model_row["audio_duration_seconds"] += audio_seconds
                model_row["total_tokens"] += total_tokens

            reason_key = (call_type, status, str(row.get("reason") or "unspecified"))
            reason_row = reasons.setdefault(
                reason_key,
                {"call_type": call_type, "status": status, "reason": reason_key[2], "events": 0},
            )
            reason_row["events"] += 1

        recent_events = [self._normalize_api_usage_event(row) for row in self.query_all(
            """
            SELECT e.*, r.name AS repeater_name
            FROM api_usage_events e
            LEFT JOIN repeaters r ON r.id = e.repeater_id
            WHERE e.created_at >= ? AND e.created_at <= ?
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT ?
            """,
            (start_time.isoformat(timespec="seconds"), end_time.isoformat(timespec="seconds"), event_limit),
        )]
        return {
            "start_time": start_time.isoformat(timespec="seconds"),
            "end_time": end_time.isoformat(timespec="seconds"),
            "bucket_minutes": int(bucket_seconds / 60),
            "buckets": buckets,
            "totals": totals,
            "call_types": sorted(
                series_by_type.values(),
                key=lambda row: (
                    {"transcription": 0, "summary": 1}.get(str(row["call_type"]), 9),
                    str(row["call_type"]),
                ),
            ),
            "models": sorted(
                models.values(),
                key=lambda row: (int(row["remote_calls"]), int(row["total_tokens"]), float(row["audio_duration_seconds"])),
                reverse=True,
            )[:10],
            "reasons": sorted(reasons.values(), key=lambda row: int(row["events"]), reverse=True)[:10],
            "recent_events": recent_events,
        }

    def upsert_push_subscription(self, endpoint: str, p256dh: str, auth: str, user_agent: str = "") -> int:
        now = utc_now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO push_subscriptions
                (endpoint, p256dh, auth, user_agent, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET
                    p256dh = excluded.p256dh,
                    auth = excluded.auth,
                    user_agent = excluded.user_agent,
                    enabled = 1,
                    updated_at = excluded.updated_at
                """,
                (endpoint, p256dh, auth, user_agent, now, now),
            )
            row = self._conn.execute(
                "SELECT id FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
            ).fetchone()
            self._conn.commit()
            return int(row["id"])

    def list_push_subscriptions(self) -> list[dict[str, Any]]:
        return [
            self._normalize_bool(row, ["enabled"])
            for row in self.query_all("SELECT * FROM push_subscriptions WHERE enabled = 1")
        ]

    def disable_push_subscription(self, endpoint: str) -> None:
        self.execute("UPDATE push_subscriptions SET enabled = 0, updated_at = ? WHERE endpoint = ?", (utc_now(), endpoint))

    def set_receiver_status(
        self,
        repeater_id: int,
        state: str,
        message: str = "",
        pid: int | None = None,
        started_at: str | None = None,
        restart_count: int | None = None,
        level_proxy: float | None = None,
    ) -> None:
        existing = self.query_one("SELECT restart_count FROM receiver_status WHERE repeater_id = ?", (repeater_id,))
        restarts = restart_count if restart_count is not None else int(existing["restart_count"]) if existing else 0
        now = utc_now()
        self.execute(
            """
            INSERT INTO receiver_status
            (repeater_id, state, message, pid, started_at, updated_at, restart_count, level_proxy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repeater_id) DO UPDATE SET
                state = excluded.state,
                message = excluded.message,
                pid = excluded.pid,
                started_at = COALESCE(excluded.started_at, receiver_status.started_at),
                updated_at = excluded.updated_at,
                restart_count = excluded.restart_count,
                level_proxy = excluded.level_proxy
            """,
            (repeater_id, state, message, pid, started_at, now, restarts, level_proxy),
        )

    def list_receiver_status(self) -> list[dict[str, Any]]:
        return self.query_all(
            """
            SELECT rs.*, r.name AS repeater_name, r.frequency_mhz
            FROM receiver_status rs
            JOIN repeaters r ON r.id = rs.repeater_id
            ORDER BY r.name
            """
        )

    def dashboard(
        self,
        activity_hours: int = 24,
        activity_bucket_minutes: int = 15,
        transcript_limit: int = 100,
        summary_limit: int = 200,
    ) -> dict[str, Any]:
        transcript_limit = max(1, int(transcript_limit))
        summary_limit = max(1, int(summary_limit))
        return {
            "repeaters": self.list_repeaters(),
            "receiver_status": self.list_receiver_status(),
            "recordings": self.list_recordings(transcript_limit),
            "activity": self.recording_activity(hours=activity_hours, bucket_minutes=activity_bucket_minutes),
            "transcripts": self.list_transcripts(transcript_limit),
            "summaries": self.list_summaries(summary_limit),
            "notification_events": self.list_notification_events(20),
            "keyword_rules": self.list_keyword_rules(),
        }

    @staticmethod
    def _normalize_bool(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        normalized = dict(row)
        for field in fields:
            if field in normalized and normalized[field] is not None:
                normalized[field] = bool(normalized[field])
        return normalized

    @staticmethod
    def _normalize_repeater(row: dict[str, Any]) -> dict[str, Any]:
        normalized = Database._normalize_bool(row, ["enabled"])
        for field, fallback in (("keyword_list", []), ("notification_settings", {})):
            value = normalized.get(field)
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    parsed = fallback
                normalized[field] = parsed if isinstance(parsed, type(fallback)) else fallback
            elif value is None:
                normalized[field] = fallback
        return normalized

    @staticmethod
    def _normalize_api_usage_event(row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        value = normalized.get("metadata")
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = {}
            normalized["metadata"] = parsed if isinstance(parsed, dict) else {}
        elif value is None:
            normalized["metadata"] = {}
        return normalized
