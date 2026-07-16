from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai_provider import base_url_allows_missing_api_key
from app.config import AppConfig, RepeaterConfig, ScanRangeConfig, SdrConfig, VoxConfig, default_config, load_config, save_config


def test_config_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    config = default_config()
    save_config(config, path)

    loaded = load_config(path)

    assert loaded.server.port == 8078
    assert loaded.repeaters[0].name == "Example 2m Repeater"


def test_repeater_frequency_and_sample_rate_validation():
    with pytest.raises(ValidationError):
        RepeaterConfig(name="bad", frequency_mhz=2.0)

    with pytest.raises(ValidationError):
        RepeaterConfig(name="bad", frequency_mhz=146.94, sample_rate=3_000_000)


def test_repeater_new_frequency_aliases_load():
    repeater = RepeaterConfig.model_validate(
        {
            "name": "Example City 146.745",
            "receive_frequency": 146.745,
            "transmit_frequency": 146.145,
            "ctcss_tone": "192.8",
            "location": "Example City, IA",
            "coverage_area": "Linn County",
            "repeater_type": "general",
        }
    )

    assert repeater.frequency_mhz == 146.745
    assert repeater.transmit_frequency_mhz == 146.145
    assert repeater.tone == "192.8"
    assert repeater.location == "Example City, IA"


def test_sdr_config_defaults_use_wide_v4_bandwidth():
    config = SdrConfig()

    assert config.multi_repeater_enabled is True
    assert config.sample_rate == 2_400_000
    assert config.guard_band_khz == 100.0


def test_vox_default_hang_time_keeps_short_gaps_together():
    config = VoxConfig()

    assert config.post_silence_seconds == 6.0


def test_ai_usage_defaults_reduce_unnecessary_remote_calls():
    config = AppConfig()

    assert config.transcription.remote_min_duration_seconds == 2.0
    assert config.transcription.remote_fallback_on_rate_limit is True
    assert config.transcription.remote_fallback_model == "gpt-4o-mini-transcribe"
    assert config.transcription.remote_fallback_low_confidence is True
    assert config.summary.scheduled_windows == ["hour", "day"]
    assert config.summary.per_repeater_scheduled is False
    assert config.summary.skip_automated_only is True
    assert config.activity_chat.backend == "noop"
    assert config.activity_chat.model == "gpt-5.4-nano"


def test_local_openai_compatible_urls_do_not_require_api_key():
    assert base_url_allows_missing_api_key("http://localhost:1234/v1")
    assert base_url_allows_missing_api_key("http://127.0.0.1:1234/v1")
    assert base_url_allows_missing_api_key("http://192.168.1.12:1234/v1")
    assert not base_url_allows_missing_api_key("https://api.openai.com/v1")


def test_duplicate_repeater_names_rejected():
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "repeaters": [
                    {"name": "Local", "frequency_mhz": 146.94},
                    {"name": "local", "frequency_mhz": 147.0},
                ]
            }
        )


def test_scan_range_validation():
    with pytest.raises(ValidationError):
        ScanRangeConfig(name="bad", start_mhz=147.0, end_mhz=146.0)
