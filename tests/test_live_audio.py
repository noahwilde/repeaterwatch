from __future__ import annotations

import asyncio

from app.audio.live import LiveAudioHub


def test_live_audio_hub_publishes_to_matching_subscribers():
    async def run() -> None:
        hub = LiveAudioHub(queue_size=2)
        first = hub.subscribe(1)
        second = hub.subscribe(2)

        hub.publish(1, b"abc")

        assert await asyncio.wait_for(first.get(), timeout=0.1) == b"abc"
        assert second.empty()

        hub.unsubscribe(1, first)
        hub.publish(1, b"def")

        assert first.empty()

    asyncio.run(run())


def test_live_audio_hub_drops_old_chunks_when_listener_lags():
    async def run() -> None:
        hub = LiveAudioHub(queue_size=1)
        queue = hub.subscribe(1)

        hub.publish(1, b"old")
        hub.publish(1, b"new")

        assert await asyncio.wait_for(queue.get(), timeout=0.1) == b"new"

    asyncio.run(run())
