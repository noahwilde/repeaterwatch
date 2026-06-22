from __future__ import annotations

import asyncio

from app.config import AppConfig
from app.db import Database
from app.notify.webpush import NotificationService, ReceiverHealthNotifier


def test_receiver_health_notifier_sends_down_once_and_recovery(tmp_path):
    db = Database(tmp_path / "rw.sqlite3")
    try:
        repeater_id = db.create_repeater({"name": "K0RPT Main", "frequency_mhz": 146.745})
        repeater = db.get_repeater(repeater_id)
        assert repeater

        notifier = ReceiverHealthNotifier(NotificationService(db, AppConfig()))

        async def run_statuses() -> None:
            await notifier.handle_status(repeater, "crashed", "rtl_fm exited")
            await notifier.handle_status(repeater, "crashed", "rtl_fm exited again")
            await notifier.handle_status(repeater, "running", "receiving")

        asyncio.run(run_statuses())

        events = db.list_notification_events()
        assert [event["source_type"] for event in events] == ["receiver_recovered", "receiver_status"]
        assert "receiver restored" in events[0]["title"]
        assert "receiver down" in events[1]["title"]
    finally:
        db.close()
