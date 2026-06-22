from __future__ import annotations

import asyncio
from collections import defaultdict


class LiveAudioHub:
    def __init__(self, queue_size: int = 32):
        self.queue_size = queue_size
        self._subscribers: dict[int, set[asyncio.Queue[bytes]]] = defaultdict(set)

    def subscribe(self, repeater_id: int) -> asyncio.Queue[bytes]:
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers[int(repeater_id)].add(queue)
        return queue

    def unsubscribe(self, repeater_id: int, queue: asyncio.Queue[bytes]) -> None:
        subscribers = self._subscribers.get(int(repeater_id))
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(int(repeater_id), None)

    def publish(self, repeater_id: int, chunk: bytes) -> None:
        if not chunk:
            return
        for queue in list(self._subscribers.get(int(repeater_id), ())):
            try:
                queue.put_nowait(chunk)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass
