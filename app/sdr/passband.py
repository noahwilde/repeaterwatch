from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import SdrConfig


@dataclass(frozen=True)
class RepeaterPassbandState:
    repeater_id: int | None
    name: str
    frequency_mhz: float
    enabled: bool
    offset_khz: float | None
    edge_margin_khz: float | None
    status: str
    message: str


def recommended_center_mhz(repeaters: list[dict[str, Any]]) -> float | None:
    enabled = [float(row["frequency_mhz"]) for row in repeaters if row.get("enabled")]
    if not enabled:
        return None
    return (min(enabled) + max(enabled)) / 2


def passband_status(repeaters: list[dict[str, Any]], sdr: SdrConfig) -> dict[str, Any]:
    enabled_frequencies = [float(row["frequency_mhz"]) for row in repeaters if row.get("enabled")]
    suggested_center = recommended_center_mhz(repeaters)
    center = float(sdr.center_frequency_mhz or suggested_center or 0.0)
    sample_rate_hz = int(sdr.sample_rate)
    sample_rate_mhz = sample_rate_hz / 1_000_000
    guard_mhz = float(sdr.guard_band_khz) / 1000
    warning_mhz = float(sdr.edge_warning_khz) / 1000
    usable_half_mhz = max(0.0, sample_rate_mhz / 2 - guard_mhz)
    lower_mhz = center - usable_half_mhz
    upper_mhz = center + usable_half_mhz
    required_span_mhz = (max(enabled_frequencies) - min(enabled_frequencies)) if enabled_frequencies else 0.0
    required_sample_rate_hz = int((required_span_mhz + 2 * guard_mhz) * 1_000_000)

    repeater_states: list[RepeaterPassbandState] = []
    for repeater in repeaters:
        enabled = bool(repeater.get("enabled"))
        frequency = float(repeater["frequency_mhz"])
        if not enabled:
            repeater_states.append(
                RepeaterPassbandState(
                    repeater_id=repeater.get("id") or repeater.get("repeater_id"),
                    name=str(repeater["name"]),
                    frequency_mhz=frequency,
                    enabled=False,
                    offset_khz=None,
                    edge_margin_khz=None,
                    status="disabled",
                    message="disabled",
                )
            )
            continue

        offset_mhz = frequency - center
        edge_margin_mhz = usable_half_mhz - abs(offset_mhz)
        if edge_margin_mhz < 0:
            status = "outside"
            message = "outside usable passband"
        elif edge_margin_mhz <= warning_mhz:
            status = "near_edge"
            message = "near passband edge"
        else:
            status = "in_range"
            message = "inside usable passband"
        repeater_states.append(
            RepeaterPassbandState(
                repeater_id=repeater.get("id") or repeater.get("repeater_id"),
                name=str(repeater["name"]),
                frequency_mhz=frequency,
                enabled=True,
                offset_khz=offset_mhz * 1000,
                edge_margin_khz=edge_margin_mhz * 1000,
                status=status,
                message=message,
            )
        )

    can_monitor = bool(enabled_frequencies) and all(row.status in {"in_range", "near_edge"} for row in repeater_states if row.enabled)
    warnings = [f"{row.name}: {row.message}" for row in repeater_states if row.status in {"near_edge", "outside"}]
    if enabled_frequencies and required_sample_rate_hz > sample_rate_hz:
        can_monitor = False
        warnings.append(
            f"Enabled repeaters require about {required_sample_rate_hz:,} Hz sample rate with guard band."
        )

    return {
        "multi_repeater_enabled": sdr.multi_repeater_enabled,
        "can_monitor": can_monitor,
        "center_frequency_mhz": center,
        "recommended_center_frequency_mhz": suggested_center,
        "sample_rate_hz": sample_rate_hz,
        "usable_bandwidth_hz": int(usable_half_mhz * 2 * 1_000_000),
        "guard_band_khz": sdr.guard_band_khz,
        "edge_warning_khz": sdr.edge_warning_khz,
        "lower_usable_mhz": lower_mhz,
        "upper_usable_mhz": upper_mhz,
        "required_sample_rate_hz": required_sample_rate_hz,
        "repeaters": [row.__dict__ for row in repeater_states],
        "warnings": warnings,
    }
