from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.audio.live import LiveAudioHub
from app.audio.segmenter import VoxSegmenter, pcm16_rms_level, write_wav
from app.config import AppConfig, VoxConfig
from app.db import Database
from app.notify.webpush import ReceiverHealthNotifier
from app.sdr.passband import passband_status
from app.sdr.rtl_fm import sanitize_filename

logger = logging.getLogger(__name__)


def build_rtl_sdr_command(center_mhz: float, sample_rate: int, repeaters: list[dict[str, Any]]) -> list[str]:
    command = [
        "rtl_sdr",
        "-f",
        str(int(center_mhz * 1_000_000)),
        "-s",
        str(int(sample_rate)),
    ]
    first = repeaters[0] if repeaters else {}
    ppm = int(first.get("ppm") or 0)
    if ppm:
        command.extend(["-p", str(ppm)])
    gain = str(first.get("gain", "auto")).strip()
    if gain and gain.lower() != "auto":
        command.extend(["-g", gain])
    command.append("-")
    return command


@dataclass
class ChannelResult:
    repeater_id: int
    level: float


class MultiIqChannel:
    def __init__(
        self,
        db: Database,
        config: AppConfig,
        repeater: dict[str, Any],
        data_dir: Path,
        center_mhz: float,
        live_audio_hub: LiveAudioHub | None = None,
    ):
        self.db = db
        self.config = config
        self.repeater = repeater
        self.data_dir = data_dir
        self.center_mhz = center_mhz
        self.source_rate = int(config.sdr.sample_rate)
        self.decimation = max(1, round(self.source_rate / int(config.vox.sample_rate)))
        self.audio_rate = max(1, int(round(self.source_rate / self.decimation)))
        self.vox_config = VoxConfig.model_validate(config.vox.model_dump() | {"sample_rate": self.audio_rate})
        self.segmenter = VoxSegmenter(self.vox_config)
        self.phase = 0.0
        self.last_baseband: np.complex64 | None = None
        self.squelch_open = False
        self.frequency_offset_hz = (float(repeater["frequency_mhz"]) - center_mhz) * 1_000_000
        self.squelch_threshold = self._squelch_threshold()
        self.live_audio_hub = live_audio_hub

    def _squelch_threshold(self) -> float:
        squelch_level = int(self.repeater.get("squelch_level") or 0)
        if squelch_level <= 0:
            return 0.0
        return max(float(self.config.vox.threshold), min(0.25, squelch_level / 1000.0))

    def process_iq(self, iq: np.ndarray, now: datetime) -> ChannelResult:
        audio = self._demodulate(iq)
        if audio.size == 0:
            return ChannelResult(int(self.repeater["id"]), 0.0)

        pcm = np.clip(audio * 22000.0, -32768, 32767).astype("<i2", copy=False).tobytes()
        level = pcm16_rms_level(pcm)
        open_now = level >= self.squelch_threshold
        if open_now != self.squelch_open:
            state = "open" if open_now else "closed"
            logger.info(
                "Multi-channel squelch %s for %s level=%.4f threshold=%.4f offset=%.1f kHz",
                state,
                self.repeater["name"],
                level,
                self.squelch_threshold,
                self.frequency_offset_hz / 1000,
            )
            self.squelch_open = open_now

        if open_now:
            if self.live_audio_hub:
                self.live_audio_hub.publish(int(self.repeater["id"]), pcm)
            for segment in self.segmenter.process(pcm, now=now):
                self._store_segment(segment)
        else:
            for segment in self.segmenter.process(b"\x00\x00" * max(1, int(self.audio_rate * self.config.vox.chunk_seconds)), now=now):
                self._store_segment(segment)
        return ChannelResult(int(self.repeater["id"]), level)

    def flush(self) -> None:
        for segment in self.segmenter.flush():
            self._store_segment(segment)

    def _demodulate(self, iq: np.ndarray) -> np.ndarray:
        usable_len = (iq.size // self.decimation) * self.decimation
        if usable_len <= self.decimation:
            return np.empty(0, dtype=np.float32)
        iq = iq[:usable_len]
        indexes = np.arange(usable_len, dtype=np.float32)
        phase_step = -2.0 * np.pi * float(self.frequency_offset_hz) / float(self.source_rate)
        oscillator = np.exp(1j * (self.phase + phase_step * indexes)).astype(np.complex64)
        self.phase = float((self.phase + phase_step * usable_len) % (2.0 * np.pi))
        mixed = iq * oscillator
        baseband = mixed.reshape(-1, self.decimation).mean(axis=1).astype(np.complex64, copy=False)
        if baseband.size < 2:
            return np.empty(0, dtype=np.float32)

        if self.last_baseband is None:
            pairs = baseband[1:] * np.conj(baseband[:-1])
        else:
            previous = np.concatenate(([self.last_baseband], baseband[:-1]))
            pairs = baseband * np.conj(previous)
        self.last_baseband = baseband[-1]
        demod = np.angle(pairs).astype(np.float32)
        demod -= float(np.mean(demod))
        peak = float(np.max(np.abs(demod))) if demod.size else 0.0
        if peak > 0:
            demod = np.clip(demod / max(peak, 0.35), -1.0, 1.0)
        return demod

    def _store_segment(self, segment: Any) -> None:
        timestamp = segment.start_time.strftime("%Y%m%dT%H%M%SZ")
        repeater_name = sanitize_filename(self.repeater["name"])
        filename = f"{timestamp}_{repeater_name}_{self.repeater['frequency_mhz']:.6f}MHz.wav"
        path = self.data_dir / "recordings" / segment.start_time.strftime("%Y") / segment.start_time.strftime("%m") / filename
        write_wav(path, segment.chunks, self.audio_rate)
        self.db.add_recording(
            {
                "repeater_id": self.repeater["id"],
                "frequency_mhz": self.repeater["frequency_mhz"],
                "repeater_name": self.repeater["name"],
                "start_time": segment.start_time.isoformat(timespec="seconds"),
                "end_time": segment.end_time.isoformat(timespec="seconds"),
                "duration_seconds": segment.duration_seconds,
                "level_proxy": segment.level_proxy,
                "audio_path": str(path),
                "status": "completed",
            }
        )
        logger.info("Stored multi-channel recording %s", path)


class MultiIqReceiver:
    def __init__(
        self,
        db: Database,
        config: AppConfig,
        repeaters: list[dict[str, Any]],
        data_dir: Path,
        health_notifier: ReceiverHealthNotifier | None = None,
        live_audio_hub: LiveAudioHub | None = None,
    ):
        self.db = db
        self.config = config
        self.repeaters = repeaters
        self.data_dir = data_dir
        self.health_notifier = health_notifier
        self.live_audio_hub = live_audio_hub
        self.stop_event = asyncio.Event()
        self.restart_count = 0
        self.passband = passband_status(repeaters, config.sdr)
        self.center_mhz = float(self.passband["center_frequency_mhz"])
        self.channels = [
            MultiIqChannel(db, config, repeater, data_dir, self.center_mhz, self.live_audio_hub)
            for repeater in repeaters
            if repeater.get("enabled")
        ]

    def live_sample_rate(self, repeater_id: int) -> int | None:
        for channel in self.channels:
            if int(channel.repeater["id"]) == int(repeater_id):
                return int(channel.audio_rate)
        return None

    async def run(self) -> None:
        backoff = 1.0
        while not self.stop_event.is_set():
            if shutil.which("rtl_sdr") is None:
                await self._set_all_status("missing", "rtl_sdr was not found in PATH", restart_count=self.restart_count)
                await asyncio.sleep(min(backoff, 60.0))
                backoff = min(backoff * 2, 60.0)
                continue

            command = build_rtl_sdr_command(self.center_mhz, int(self.config.sdr.sample_rate), self.repeaters)
            await self._set_all_status("starting", "starting shared rtl_sdr IQ source", restart_count=self.restart_count)
            logger.info("Starting shared rtl_sdr receiver: %s", " ".join(command))
            process: asyncio.subprocess.Process | None = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await self._set_all_status(
                    "running",
                    self._status_message(),
                    pid=process.pid,
                    started_at=datetime.now(UTC).isoformat(timespec="seconds"),
                    restart_count=self.restart_count,
                )
                await self._consume_iq(process)
                stderr = await self._drain_stderr(process)
                exit_code = await process.wait()
                if self.stop_event.is_set():
                    break
                self.restart_count += 1
                await self._set_all_status(
                    "crashed",
                    f"rtl_sdr exited with {exit_code}: {stderr[-500:]}",
                    restart_count=self.restart_count,
                )
                logger.warning("Shared rtl_sdr exited: %s", stderr)
            except asyncio.CancelledError:
                if process:
                    process.terminate()
                raise
            except Exception as exc:
                self.restart_count += 1
                await self._set_all_status("error", str(exc), restart_count=self.restart_count)
                logger.exception("Shared multi-channel receiver failed")
            finally:
                if process and process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
        for channel in self.channels:
            channel.flush()
        await self._set_all_status("stopped", "receiver stopped", restart_count=self.restart_count)

    def stop(self) -> None:
        self.stop_event.set()

    async def _consume_iq(self, process: asyncio.subprocess.Process) -> None:
        assert process.stdout is not None
        chunk_size = max(4096, int(self.config.sdr.sample_rate * 2 * self.config.sdr.source_chunk_seconds))
        chunk_size -= chunk_size % 2
        while not self.stop_event.is_set():
            raw = await process.stdout.read(chunk_size)
            if not raw:
                break
            iq = self._bytes_to_iq(raw)
            if iq.size == 0:
                continue
            now = datetime.now(UTC)
            for channel in self.channels:
                result = channel.process_iq(iq, now)
                self.db.set_receiver_status(
                    result.repeater_id,
                    "running",
                    self._status_message(channel),
                    pid=process.pid,
                    restart_count=self.restart_count,
                    level_proxy=result.level,
                )

    def _bytes_to_iq(self, raw: bytes) -> np.ndarray:
        if len(raw) < 4:
            return np.empty(0, dtype=np.complex64)
        usable = raw[: len(raw) - (len(raw) % 2)]
        values = np.frombuffer(usable, dtype=np.uint8).astype(np.float32)
        i = (values[0::2] - 127.5) / 127.5
        q = (values[1::2] - 127.5) / 127.5
        return (i + 1j * q).astype(np.complex64, copy=False)

    async def _drain_stderr(self, process: asyncio.subprocess.Process) -> str:
        if process.stderr is None:
            return ""
        try:
            data = await asyncio.wait_for(process.stderr.read(), timeout=1)
        except asyncio.TimeoutError:
            return ""
        return data.decode("utf-8", errors="replace")

    async def _set_all_status(
        self,
        state: str,
        message: str,
        pid: int | None = None,
        started_at: str | None = None,
        restart_count: int | None = None,
    ) -> None:
        for repeater in self.repeaters:
            self.db.set_receiver_status(
                int(repeater["id"]),
                state,
                message,
                pid=pid,
                started_at=started_at,
                restart_count=restart_count,
            )
            if self.health_notifier:
                await self.health_notifier.handle_status(repeater, state, message)

    def _status_message(self, channel: MultiIqChannel | None = None) -> str:
        if channel is None:
            return (
                f"shared IQ receiver center {self.center_mhz:.6f} MHz, "
                f"sample rate {int(self.config.sdr.sample_rate):,} Hz"
            )
        return (
            f"shared IQ offset {channel.frequency_offset_hz / 1000:.1f} kHz, "
            f"audio {channel.audio_rate:,} Hz"
        )
