from __future__ import annotations

from app.config import SdrConfig
from app.sdr.passband import passband_status, recommended_center_mhz


def test_recommended_center_ignores_disabled_repeaters():
    repeaters = [
        {"id": 1, "name": "A", "frequency_mhz": 146.745, "enabled": True},
        {"id": 2, "name": "B", "frequency_mhz": 146.945, "enabled": True},
        {"id": 3, "name": "Disabled", "frequency_mhz": 147.945, "enabled": False},
    ]

    assert recommended_center_mhz(repeaters) == 146.845


def test_passband_marks_repeaters_in_range_near_edge_and_outside():
    sdr = SdrConfig(sample_rate=960_000, center_frequency_mhz=146.5, guard_band_khz=100, edge_warning_khz=60)
    repeaters = [
        {"id": 1, "name": "Center", "frequency_mhz": 146.5, "enabled": True},
        {"id": 2, "name": "Edge", "frequency_mhz": 146.86, "enabled": True},
        {"id": 3, "name": "Outside", "frequency_mhz": 146.95, "enabled": True},
        {"id": 4, "name": "Disabled", "frequency_mhz": 148.0, "enabled": False},
    ]

    status = passband_status(repeaters, sdr)
    by_name = {row["name"]: row for row in status["repeaters"]}

    assert by_name["Center"]["status"] == "in_range"
    assert by_name["Edge"]["status"] == "near_edge"
    assert by_name["Outside"]["status"] == "outside"
    assert by_name["Disabled"]["status"] == "disabled"
    assert status["can_monitor"] is False


def test_passband_can_monitor_when_enabled_repeaters_fit():
    sdr = SdrConfig(sample_rate=960_000, guard_band_khz=100)
    repeaters = [
        {"id": 1, "name": "Low", "frequency_mhz": 146.745, "enabled": True},
        {"id": 2, "name": "High", "frequency_mhz": 147.0, "enabled": True},
    ]

    status = passband_status(repeaters, sdr)

    assert status["can_monitor"] is True
    assert status["recommended_center_frequency_mhz"] == 146.8725
    assert status["center_frequency_mhz"] == 146.8725
