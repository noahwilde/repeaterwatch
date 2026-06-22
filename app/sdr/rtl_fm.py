from __future__ import annotations

import asyncio
import logging
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.audio.live import LiveAudioHub
from app.audio.segmenter import VoxSegmenter, write_wav
from app.config import AppConfig
from app.db import Database
from app.notify.webpush import ReceiverHealthNotifier

logger = logging.getLogger(__name__)


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return sanitized.strip("-") or "repeater"


def build_rtl_fm_command(repeater: dict[str, Any], config: AppConfig) -> list[str]:
    frequency = f"{repeater['frequency_mhz']:.6f}M"
    sample_rate = int(repeater.get("sample_rate") or config.vox.sample_rate)
    command = [
        "rtl_fm",
        "-M",
        "fm",
        "-f",
        frequency,
        "-s",
        str(sample_rate),
        "-l",
        str(repeater.get("squelch_level", 50)),
        "-p",
        str(repeater.get("ppm", 0)),
        "-F",
        "9",
        "-E",
        "offset",
        "-E",
        "dc",
        "-E",
        "deemp",
    ]
    gain = str(repeater.get("gain", "auto")).strip()
    if gain and gain.lower() != "auto":
        command.extend(["-g", gain])
    command.append("-")
    return command


class RtlFmReceiver:
    def __init__(
        self,
        db: Database,
        config: AppConfig,
        repeater: dict[str, Any],
        data_dir: Path,
        health_notifier: ReceiverHealthNotifier | None = None,
        live_audio_hub: LiveAudioHub | None = None,
    ):
        self.db = db
        self.config = config
        self.repeater = repeater
        self.data_dir = data_dir
        self.health_notifier = health_notifier
        self.live_audio_hub = live_audio_hub
        self.stop_event = asyncio.Event()
        self.restart_count = 0

    async def _set_status(
        self,
        state: str,
        message: str = "",
        pid: int | None = None,
        started_at: str | None = None,
        restart_count: int | None = None,
        level_proxy: float | None = None,
    ) -> None:
        self.db.set_receiver_status(
            int(self.repeater["id"]),
            state,
            message,
            pid=pid,
            started_at=started_at,
            restart_count=restart_count,
            level_proxy=level_proxy,
        )
        if self.health_notifier:
            await self.health_notifier.handle_status(self.repeater, state, message)

    async def run(self) -> None:
        repeater_id = int(self.repeater["id"])
        backoff = 1.0
        while not self.stop_event.is_set():
            if shutil.which("rtl_fm") is None:
                await self._set_status(
                    "missing",
                    "rtl_fm was not found in PATH",
                    restart_count=self.restart_count,
                )
                await asyncio.sleep(min(backoff, 60.0))
                backoff = min(backoff * 2, 60.0)
                continue

            command = build_rtl_fm_command(self.repeater, self.config)
            await self._set_status(
                "starting",
                "starting rtl_fm",
                restart_count=self.restart_count,
            )
            logger.info("Starting rtl_fm for %s: %s", self.repeater["name"], " ".join(command))
            process: asyncio.subprocess.Process | None = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await self._set_status(
                    "running",
                    "receiving",
                    pid=process.pid,
                    started_at=datetime.now(UTC).isoformat(timespec="seconds"),
                    restart_count=self.restart_count,
                )
                await self._consume_audio(process)
                stderr = await self._drain_stderr(process)
                exit_code = await process.wait()
                if self.stop_event.is_set():
                    break
                if exit_code == 0:
                    await self._set_status(
                        "stopped",
                        "rtl_fm exited cleanly",
                        restart_count=self.restart_count,
                    )
                    logger.info("rtl_fm exited cleanly for %s", self.repeater["name"])
                else:
                    self.restart_count += 1
                    await self._set_status(
                        "crashed",
                        f"rtl_fm exited with {exit_code}: {stderr[-500:]}",
                        restart_count=self.restart_count,
                    )
                    logger.warning("rtl_fm exited for %s: %s", self.repeater["name"], stderr)
            except asyncio.CancelledError:
                if process:
                    process.terminate()
                raise
            except Exception as exc:
                self.restart_count += 1
                await self._set_status(
                    "error",
                    str(exc),
                    restart_count=self.restart_count,
                )
                logger.exception("Receiver failed for %s", self.repeater["name"])
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
        await self._set_status("stopped", "receiver stopped", restart_count=self.restart_count)

    def stop(self) -> None:
        self.stop_event.set()

    async def _consume_audio(self, process: asyncio.subprocess.Process) -> None:
        assert process.stdout is not None
        segmenter = VoxSegmenter(self.config.vox)
        chunk_size = max(1024, int(self.config.vox.sample_rate * 2 * self.config.vox.chunk_seconds))
        while not self.stop_event.is_set():
            chunk = await process.stdout.read(chunk_size)
            if not chunk:
                break
            if self.live_audio_hub:
                self.live_audio_hub.publish(int(self.repeater["id"]), chunk)
            for segment in segmenter.process(chunk):
                self._store_segment(segment)
                await self._set_status(
                    "running",
                    "activity recorded",
                    pid=process.pid,
                    restart_count=self.restart_count,
                    level_proxy=segment.level_proxy,
                )
        for segment in segmenter.flush():
            self._store_segment(segment)

    async def _drain_stderr(self, process: asyncio.subprocess.Process) -> str:
        if process.stderr is None:
            return ""
        try:
            data = await asyncio.wait_for(process.stderr.read(), timeout=1)
        except asyncio.TimeoutError:
            return ""
        return data.decode("utf-8", errors="replace")

    def _store_segment(self, segment: Any) -> None:
        timestamp = segment.start_time.strftime("%Y%m%dT%H%M%SZ")
        repeater_name = sanitize_filename(self.repeater["name"])
        filename = f"{timestamp}_{repeater_name}_{self.repeater['frequency_mhz']:.6f}MHz.wav"
        path = self.data_dir / "recordings" / segment.start_time.strftime("%Y") / segment.start_time.strftime("%m") / filename
        write_wav(path, segment.chunks, self.config.vox.sample_rate)
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
        logger.info("Stored recording %s", path)
