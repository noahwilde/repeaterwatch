from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_RTL_SDR_SAMPLE_RATE = 2_400_000
MIN_RTL_SDR_MHZ = 24.0
MAX_RTL_SDR_MHZ = 1_766.0


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=8078, ge=1, le=65535)
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None


class StorageConfig(BaseModel):
    data_dir: str = "data"

    def resolved_data_dir(self, config_path: Path | None = None) -> Path:
        path = Path(self.data_dir).expanduser()
        if path.is_absolute() or config_path is None:
            return path
        return (config_path.parent / path).resolve()


class RepeaterConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = Field(min_length=1, max_length=120)
    frequency_mhz: float = Field(gt=0, validation_alias=AliasChoices("frequency_mhz", "receive_frequency", "receive_frequency_mhz"))
    transmit_frequency_mhz: float | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("transmit_frequency_mhz", "transmit_frequency", "tx_frequency_mhz"),
    )
    offset_mhz: float | None = None
    tone: str | None = Field(default=None, validation_alias=AliasChoices("tone", "ctcss_tone"))
    mode: Literal["NFM"] = "NFM"
    squelch_level: int = Field(default=50, ge=0, le=200)
    sample_rate: int = Field(default=24_000, ge=8_000, le=MAX_RTL_SDR_SAMPLE_RATE)
    gain: str = "auto"
    ppm: int = Field(default=0, ge=-200, le=200)
    enabled: bool = True
    description: str | None = None
    location: str | None = None
    coverage_area: str | None = None
    repeater_type: str | None = None
    notes: str | None = None
    keyword_list: list[str] = Field(default_factory=list)
    notification_settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("frequency_mhz")
    @classmethod
    def frequency_in_rtl_sdr_range(cls, value: float) -> float:
        if not (MIN_RTL_SDR_MHZ <= value <= MAX_RTL_SDR_MHZ):
            raise ValueError(
                f"frequency must be between {MIN_RTL_SDR_MHZ} and {MAX_RTL_SDR_MHZ} MHz"
            )
        return value


class SdrConfig(BaseModel):
    multi_repeater_enabled: bool = True
    sample_rate: int = Field(default=2_400_000, ge=240_000, le=MAX_RTL_SDR_SAMPLE_RATE)
    center_frequency_mhz: float | None = Field(default=None, gt=0)
    guard_band_khz: float = Field(default=100.0, ge=0, le=500.0)
    edge_warning_khz: float = Field(default=50.0, ge=0, le=500.0)
    source_chunk_seconds: float = Field(default=0.25, ge=0.05, le=1.0)

    @field_validator("center_frequency_mhz")
    @classmethod
    def center_in_rtl_sdr_range(cls, value: float | None) -> float | None:
        if value is not None and not (MIN_RTL_SDR_MHZ <= value <= MAX_RTL_SDR_MHZ):
            raise ValueError(
                f"center_frequency_mhz must be between {MIN_RTL_SDR_MHZ} and {MAX_RTL_SDR_MHZ} MHz"
            )
        return value


class ScanRangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    start_mhz: float = Field(gt=0)
    end_mhz: float = Field(gt=0)
    channel_step_khz: float = Field(default=12.5, gt=0)
    dwell_seconds: float = Field(default=1.0, ge=0.2)
    squelch_threshold: int = Field(default=50, ge=0, le=200)
    enabled: bool = False

    @model_validator(mode="after")
    def validate_range(self) -> "ScanRangeConfig":
        if self.start_mhz >= self.end_mhz:
            raise ValueError("scan range start_mhz must be lower than end_mhz")
        for value in (self.start_mhz, self.end_mhz):
            if not (MIN_RTL_SDR_MHZ <= value <= MAX_RTL_SDR_MHZ):
                raise ValueError(
                    f"scan frequencies must be between {MIN_RTL_SDR_MHZ} and {MAX_RTL_SDR_MHZ} MHz"
                )
        span_khz = (self.end_mhz - self.start_mhz) * 1000
        if span_khz / self.channel_step_khz > 10_000:
            raise ValueError("scan range contains too many channels")
        return self


class VoxConfig(BaseModel):
    pre_roll_seconds: float = Field(default=1.0, ge=0, le=10)
    post_silence_seconds: float = Field(default=6.0, ge=0.1, le=30)
    min_duration_seconds: float = Field(default=1.0, ge=0.1, le=60)
    max_duration_seconds: float = Field(default=180.0, ge=5, le=3600)
    threshold: float = Field(default=0.018, gt=0, le=1)
    sample_rate: int = Field(default=24_000, ge=8_000, le=96_000)
    chunk_seconds: float = Field(default=0.25, ge=0.05, le=2)


class TranscriptionConfig(BaseModel):
    backend: Literal["noop", "faster-whisper", "openai-compatible"] = "noop"
    model: str = "base"
    language: str | None = "en"
    compute_type: str = "int8"
    remote_base_url: str = "https://api.openai.com/v1"
    remote_api_key_env: str = "OPENAI_API_KEY"
    remote_model: str = "whisper-1"
    remote_fallback_on_rate_limit: bool = True
    remote_fallback_model: str = "gpt-4o-mini-transcribe"
    remote_fallback_low_confidence: bool = True
    remote_min_duration_seconds: float = Field(default=2.0, ge=0, le=60)
    poll_seconds: float = Field(default=5.0, ge=1)


SummaryScheduledWindow = Literal["quarter_hour", "hour", "day"]


class SummaryConfig(BaseModel):
    backend: Literal["noop", "openai-compatible", "ollama"] = "noop"
    model: str = "llama3.1"
    base_url: str = "http://localhost:11434"
    api_key_env: str = "OPENAI_API_KEY"
    timezone: str = "local"
    prompt_version: str = "repeaterwatch-v6-scheduled-timeline"
    min_transcripts: int = Field(default=1, ge=1)
    scheduled_windows: list[SummaryScheduledWindow] = Field(
        default_factory=lambda: ["hour", "day"]
    )
    per_repeater_scheduled: bool = False
    skip_automated_only: bool = True
    schedule_delay_seconds: float = Field(default=120.0, ge=0, le=3600)
    max_prompt_chars: int = Field(default=60_000, ge=4_000, le=200_000)
    poll_seconds: float = Field(default=60.0, ge=10)


class ActivityChatConfig(BaseModel):
    backend: Literal["noop", "openai-compatible", "ollama"] = "noop"
    model: str = "gpt-5.4-nano"
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    timezone: str = "local"
    prompt_version: str = "repeaterwatch-activity-chat-v3"
    default_hours: int = Field(default=24, ge=1, le=24 * 30)
    max_history_messages: int = Field(default=12, ge=0, le=40)
    max_transcripts: int = Field(default=60, ge=1, le=250)
    max_summaries: int = Field(default=20, ge=0, le=100)
    max_context_chars: int = Field(default=30_000, ge=4_000, le=120_000)


class NotificationConfig(BaseModel):
    enabled: bool = True
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    subject: str = "mailto:admin@example.local"


class RetentionConfig(BaseModel):
    raw_audio_days: int = Field(default=30, ge=1)
    transcripts_days: int = Field(default=365, ge=1)
    summaries_days: int = Field(default=365, ge=1)
    transcript_display_limit: int = Field(default=100, ge=1, le=1000)
    summary_display_limit: int = Field(default=200, ge=1, le=2000)
    delete_metadata_without_summary: bool = False


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server: ServerConfig = Field(default_factory=ServerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    sdr: SdrConfig = Field(default_factory=SdrConfig)
    repeaters: list[RepeaterConfig] = Field(default_factory=list)
    scan_ranges: list[ScanRangeConfig] = Field(default_factory=list)
    vox: VoxConfig = Field(default_factory=VoxConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    summary: SummaryConfig = Field(default_factory=SummaryConfig)
    activity_chat: ActivityChatConfig = Field(default_factory=ActivityChatConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)

    @model_validator(mode="after")
    def validate_repeater_names(self) -> "AppConfig":
        names = [repeater.name.strip().casefold() for repeater in self.repeaters]
        if len(names) != len(set(names)):
            raise ValueError("repeater names must be unique")
        return self


def default_config() -> AppConfig:
    return AppConfig(
        repeaters=[
            RepeaterConfig(
                name="Example 2m Repeater",
                frequency_mhz=146.94,
                enabled=False,
            )
        ]
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).expanduser()
    if not config_path.exists():
        return default_config()
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return AppConfig.model_validate(raw)


def save_config(config: AppConfig, path: str | Path) -> None:
    import tomli_w

    config_path = Path(path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json", exclude_none=True)
    with tempfile.NamedTemporaryFile(
        "wb", delete=False, dir=str(config_path.parent), prefix=f".{config_path.name}.", suffix=".tmp"
    ) as handle:
        handle.write(tomli_w.dumps(data).encode("utf-8"))
        temp_name = handle.name
    os.replace(temp_name, config_path)


def public_config(config: AppConfig) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    data["notifications"]["vapid_private_key"] = ""
    for section, field in (
        ("transcription", "remote_api_key_env"),
        ("summary", "api_key_env"),
        ("activity_chat", "api_key_env"),
    ):
        value = data.get(section, {}).get(field, "")
        if isinstance(value, str) and (value.startswith("sk-") or len(value) > 80):
            data[section][field] = ""
    return data
