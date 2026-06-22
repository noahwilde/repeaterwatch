from __future__ import annotations

from pathlib import Path

import numpy as np

from app.config import AppConfig
from app.db import Database
from app.sdr.multi_iq import MultiIqChannel, build_rtl_sdr_command


def _fm_carrier(source_rate: int, seconds: float, offset_hz: float, tone_hz: float, deviation_hz: float = 5_000) -> np.ndarray:
    samples = int(source_rate * seconds)
    t = np.arange(samples, dtype=np.float32) / source_rate
    audio = np.sin(2 * np.pi * tone_hz * t)
    instantaneous = offset_hz + deviation_hz * audio
    phase = np.cumsum(2 * np.pi * instantaneous / source_rate)
    return np.exp(1j * phase).astype(np.complex64)


def _channel(db: Database, config: AppConfig, frequency_mhz: float, tmp_path: Path) -> MultiIqChannel:
    repeater = {
        "id": int(round(frequency_mhz * 1000)),
        "name": f"{frequency_mhz:.3f}",
        "frequency_mhz": frequency_mhz,
        "squelch_level": 0,
    }
    return MultiIqChannel(db, config, repeater, tmp_path, center_mhz=146.9)


def test_build_rtl_sdr_command_uses_one_iq_source():
    command = build_rtl_sdr_command(146.9, 960_000, [{"gain": "30", "ppm": 1}])

    assert command[:5] == ["rtl_sdr", "-f", "146900000", "-s", "960000"]
    assert "-g" in command
    assert command[-1] == "-"


def test_channelizer_isolates_synthetic_fm_carriers(tmp_path):
    config = AppConfig.model_validate(
        {
            "sdr": {"sample_rate": 240_000, "guard_band_khz": 25},
            "vox": {
                "sample_rate": 24_000,
                "threshold": 0.005,
                "min_duration_seconds": 0.1,
                "post_silence_seconds": 0.2,
                "pre_roll_seconds": 0,
            },
        }
    )
    db = Database(tmp_path / "rw.sqlite3")
    try:
        source_rate = config.sdr.sample_rate
        desired = _fm_carrier(source_rate, 0.5, -30_000, 1000)
        other = _fm_carrier(source_rate, 0.5, 30_000, 2200)
        iq = ((desired + other) / 2).astype(np.complex64)

        low = _channel(db, config, 146.870, tmp_path)
        high = _channel(db, config, 146.930, tmp_path)
        low_audio = low._demodulate(iq)
        high_audio = high._demodulate(iq)

        assert low_audio.size > 0
        assert high_audio.size > 0
        assert float(np.sqrt(np.mean(low_audio * low_audio))) > 0.05
        assert float(np.sqrt(np.mean(high_audio * high_audio))) > 0.05
        assert abs(float(np.corrcoef(low_audio[: high_audio.size], high_audio)[0, 1])) < 0.8
    finally:
        db.close()
