from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.audio.live import LiveAudioHub
from app.config import AppConfig
from app.db import Database
from app.notify.webpush import ReceiverHealthNotifier
from app.sdr.multi_iq import MultiIqReceiver
from app.sdr.passband import passband_status
from app.sdr.rtl_fm import RtlFmReceiver

logger = logging.getLogger(__name__)


class ReceiverManager:
    def __init__(
        self,
        db: Database,
        config: AppConfig,
        data_dir: Path,
        health_notifier: ReceiverHealthNotifier | None = None,
    ):
        self.db = db
        self.config = config
        self.data_dir = data_dir
        self.health_notifier = health_notifier
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._receivers: dict[int, RtlFmReceiver] = {}
        self._multi_receiver: MultiIqReceiver | None = None
        self._multi_task: asyncio.Task[None] | None = None
        self._multi_ids: set[int] = set()
        self.live_audio_hub = LiveAudioHub()

    async def sync(self) -> None:
        enabled_repeaters = {int(row["id"]): row for row in self.db.list_repeaters(enabled=True)}
        if len(enabled_repeaters) > 1 and self.config.sdr.multi_repeater_enabled:
            await self._sync_multi(enabled_repeaters)
            return

        await self._stop_multi()
        for repeater_id in list(self._tasks):
            if repeater_id not in enabled_repeaters:
                await self.stop_repeater(repeater_id)
        for repeater_id, repeater in enabled_repeaters.items():
            task = self._tasks.get(repeater_id)
            if task and not task.done():
                continue
            receiver = RtlFmReceiver(
                self.db,
                self.config,
                repeater,
                self.data_dir,
                self.health_notifier,
                self.live_audio_hub,
            )
            self._receivers[repeater_id] = receiver
            self._tasks[repeater_id] = asyncio.create_task(receiver.run(), name=f"rtl-fm-{repeater_id}")
            logger.info("Receiver task started for %s", repeater["name"])

    async def _sync_multi(self, enabled_repeaters: dict[int, dict]) -> None:
        for repeater_id in list(self._tasks):
            await self.stop_repeater(repeater_id)

        repeaters = list(enabled_repeaters.values())
        status = passband_status(repeaters, self.config.sdr)
        if not status["can_monitor"]:
            await self._stop_multi()
            message = self._passband_error_message(status)
            for repeater_id, repeater in enabled_repeaters.items():
                repeater_status = next((row for row in status["repeaters"] if row["repeater_id"] == repeater_id), None)
                state = "outside_range" if repeater_status and repeater_status["status"] == "outside" else "error"
                self.db.set_receiver_status(repeater_id, state, message)
            logger.warning("Shared receiver not started: %s", message)
            return

        repeater_ids = set(enabled_repeaters)
        if self._multi_task and not self._multi_task.done() and repeater_ids == self._multi_ids:
            return

        await self._stop_multi()
        self._multi_receiver = MultiIqReceiver(
            self.db,
            self.config,
            repeaters,
            self.data_dir,
            self.health_notifier,
            self.live_audio_hub,
        )
        self._multi_ids = repeater_ids
        self._multi_task = asyncio.create_task(self._multi_receiver.run(), name="rtl-sdr-shared")
        logger.info("Shared receiver task started for %s repeaters", len(repeaters))

    def live_sample_rate(self, repeater_id: int) -> int:
        repeater_id = int(repeater_id)
        receiver = self._receivers.get(repeater_id)
        if receiver:
            return int(receiver.repeater.get("sample_rate") or self.config.vox.sample_rate)
        if self._multi_receiver:
            sample_rate = self._multi_receiver.live_sample_rate(repeater_id)
            if sample_rate:
                return sample_rate
        repeater = self.db.get_repeater(repeater_id)
        if repeater:
            return int(repeater.get("sample_rate") or self.config.vox.sample_rate)
        return int(self.config.vox.sample_rate)

    def _passband_error_message(self, status: dict) -> str:
        recommended = status.get("recommended_center_frequency_mhz")
        required = status.get("required_sample_rate_hz")
        message = "enabled repeaters do not fit inside the usable SDR passband"
        if recommended:
            message += f"; suggested center {recommended:.6f} MHz"
        if required:
            message += f"; required sample rate about {required:,} Hz"
        return message

    async def stop_repeater(self, repeater_id: int) -> None:
        if repeater_id in self._multi_ids:
            await self._stop_multi()
            self.db.set_receiver_status(repeater_id, "stopped", "receiver stopped")
            return
        receiver = self._receivers.pop(repeater_id, None)
        task = self._tasks.pop(repeater_id, None)
        if receiver:
            receiver.stop()
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.db.set_receiver_status(repeater_id, "stopped", "receiver stopped")

    async def stop_all(self) -> None:
        await self._stop_multi()
        for repeater_id in list(self._tasks):
            await self.stop_repeater(repeater_id)

    async def _stop_multi(self) -> None:
        receiver = self._multi_receiver
        task = self._multi_task
        repeater_ids = list(self._multi_ids)
        self._multi_receiver = None
        self._multi_task = None
        self._multi_ids = set()
        if receiver:
            receiver.stop()
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        for repeater_id in repeater_ids:
            self.db.set_receiver_status(repeater_id, "stopped", "receiver stopped")
