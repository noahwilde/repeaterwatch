from __future__ import annotations

from pydantic import BaseModel, Field


class RepeaterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    frequency_mhz: float = Field(gt=0)
    transmit_frequency_mhz: float | None = Field(default=None, gt=0)
    offset_mhz: float | None = None
    tone: str | None = None
    mode: str = "NFM"
    squelch_level: int = Field(default=50, ge=0, le=200)
    sample_rate: int = Field(default=24_000, ge=8_000)
    gain: str = "auto"
    ppm: int = Field(default=0, ge=-200, le=200)
    enabled: bool = True
    description: str | None = None
    location: str | None = None
    coverage_area: str | None = None
    repeater_type: str | None = None
    notes: str | None = None


class RepeaterOut(RepeaterIn):
    id: int


class RecordingOut(BaseModel):
    id: int
    repeater_id: int | None
    repeater_name: str
    frequency_mhz: float
    start_time: str
    end_time: str | None
    duration_seconds: float | None
    level_proxy: float | None
    audio_path: str
    status: str
    error: str | None = None


class TranscriptOut(BaseModel):
    id: int
    recording_id: int
    text: str
    original_text: str
    corrected_text: str | None = None
    confidence: float | None = None
    low_confidence: bool
    status: str
    backend: str


class TranscriptCorrectionIn(BaseModel):
    corrected_text: str = Field(min_length=1)


class KeywordRuleIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=500)
    is_regex: bool = False
    case_sensitive: bool = False
    repeater_id: int | None = None
    notify_transcript: bool = True
    notify_summary: bool = False
    cooldown_minutes: int = Field(default=10, ge=0, le=24 * 60)
    enabled: bool = True


class KeywordRuleOut(KeywordRuleIn):
    id: int


class TrafficAlertSettingsIn(BaseModel):
    enabled: bool = False
    suppress_phrases: str = ""


class PushSubscriptionIn(BaseModel):
    endpoint: str
    keys: dict[str, str]
    user_agent: str = ""


class SummaryRequest(BaseModel):
    window_name: str = "quarter_hour"
    repeater_id: int | None = None


class TestNotificationIn(BaseModel):
    title: str = "RepeaterWatch test"
    body: str = "Notifications are configured."
