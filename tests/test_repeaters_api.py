from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.api.repeaters import delete_repeater
from app.config import AppConfig
from app.db import Database


class FakeReceiverManager:
    def __init__(self) -> None:
        self.stopped: list[int] = []
        self.sync_count = 0
        self.config = None

    async def stop_repeater(self, repeater_id: int) -> None:
        self.stopped.append(repeater_id)

    async def sync(self) -> None:
        self.sync_count += 1


def test_delete_repeater_resyncs_remaining_receivers(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        kept_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745})
        deleted_id = db.create_repeater({"name": "Test", "frequency_mhz": 146.8})
        manager = FakeReceiverManager()
        worker = SimpleNamespace(config=None, service=SimpleNamespace(config=None))
        state = SimpleNamespace(
            db=db,
            config=AppConfig(),
            config_path=tmp_path / "config.toml",
            receiver_manager=manager,
            notification_service=SimpleNamespace(config=None),
            summary_service=SimpleNamespace(config=None),
            transcription_worker=worker,
            summary_worker=worker,
        )
        request = SimpleNamespace(app=SimpleNamespace(state=state))

        result = asyncio.run(delete_repeater(deleted_id, request))

        assert result == {"status": "deleted"}
        assert manager.stopped == [deleted_id]
        assert manager.sync_count == 1
        assert db.get_repeater(deleted_id) is None
        assert db.get_repeater(kept_id) is not None
    finally:
        db.close()
