from __future__ import annotations

import asyncio
import shutil
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import RepeaterConfig
from app.sdr.rtl_fm import build_rtl_fm_command

router = APIRouter(tags=["live-test"])


def _tail(buffer: list[str], max_chars: int = 800) -> str:
    return "".join(buffer)[-max_chars:].strip()


async def _collect_stderr(process: asyncio.subprocess.Process, buffer: list[str]) -> None:
    if process.stderr is None:
        return
    while True:
        chunk = await process.stderr.read(1024)
        if not chunk:
            return
        buffer.append(chunk.decode("utf-8", errors="replace"))
        if len(buffer) > 20:
            del buffer[: len(buffer) - 20]


async def _terminate(process: asyncio.subprocess.Process | None) -> None:
    if process is None or process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


@router.websocket("/api/live-test/ws")
async def live_test_ws(
    websocket: WebSocket,
    frequency_mhz: float,
    squelch_level: int = 0,
    gain: str = "auto",
    ppm: int = 0,
    sample_rate: int = 24_000,
) -> None:
    await websocket.accept()
    config = websocket.app.state.config
    receiver_manager = websocket.app.state.receiver_manager
    process: asyncio.subprocess.Process | None = None
    stderr_task: asyncio.Task[None] | None = None
    stderr_buffer: list[str] = []

    try:
        RepeaterConfig.model_validate(
            {
                "name": "live-test",
                "frequency_mhz": frequency_mhz,
                "squelch_level": squelch_level,
                "sample_rate": sample_rate,
                "gain": gain,
                "ppm": ppm,
                "enabled": False,
            }
        )
        if shutil.which("rtl_fm") is None:
            await websocket.send_json({"type": "error", "message": "rtl_fm was not found in PATH"})
            return

        repeater: dict[str, Any] = {
            "name": "live-test",
            "frequency_mhz": frequency_mhz,
            "squelch_level": squelch_level,
            "sample_rate": sample_rate,
            "gain": gain,
            "ppm": ppm,
        }
        await receiver_manager.stop_all()
        command = build_rtl_fm_command(repeater, config)
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stderr_task = asyncio.create_task(_collect_stderr(process, stderr_buffer))
        chunk_size = max(1024, int(sample_rate * 2 * 0.1))
        await websocket.send_json(
            {
                "type": "started",
                "sample_rate": sample_rate,
                "command": " ".join(command),
                "message": "Live test started. Normal receivers are paused until the test stops.",
            }
        )

        assert process.stdout is not None
        while process.returncode is None:
            try:
                chunk = await asyncio.wait_for(process.stdout.read(chunk_size), timeout=0.5)
            except asyncio.TimeoutError:
                return_code = process.returncode
                stderr = _tail(stderr_buffer)
                if return_code is not None:
                    await websocket.send_json(
                        {
                            "type": "stopped",
                            "return_code": return_code,
                            "message": stderr or f"rtl_fm exited with {return_code}",
                        }
                    )
                    break
                message = "No audio from rtl_fm. If squelch is above 0, it may be closed."
                if stderr:
                    message = f"{message} rtl_fm says: {stderr}"
                await websocket.send_json(
                    {
                        "type": "level",
                        "level": 0.0,
                        "active": False,
                        "message": message,
                    }
                )
                continue
            if not chunk:
                break
            await websocket.send_bytes(chunk)

        return_code = await process.wait()
        message = _tail(stderr_buffer) or f"rtl_fm exited with {return_code}"
        await websocket.send_json({"type": "stopped", "return_code": return_code, "message": message})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except RuntimeError:
            pass
    finally:
        if stderr_task:
            stderr_task.cancel()
            await asyncio.gather(stderr_task, return_exceptions=True)
        await _terminate(process)
        await receiver_manager.sync()


@router.websocket("/api/live-listen/ws")
async def live_listen_ws(websocket: WebSocket, repeater_id: int) -> None:
    await websocket.accept()
    db = websocket.app.state.db
    receiver_manager = websocket.app.state.receiver_manager
    repeater = db.get_repeater(int(repeater_id))
    if not repeater:
        await websocket.send_json({"type": "error", "message": "Repeater not found"})
        return
    if not repeater.get("enabled"):
        await websocket.send_json({"type": "error", "message": "Repeater is disabled"})
        return

    sample_rate = receiver_manager.live_sample_rate(int(repeater_id))
    queue = receiver_manager.live_audio_hub.subscribe(int(repeater_id))
    try:
        await websocket.send_json(
            {
                "type": "started",
                "sample_rate": sample_rate,
                "message": "Listening to the active receiver. Recording and transcription continue.",
            }
        )
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                await websocket.send_json(
                    {
                        "type": "waiting",
                        "sample_rate": sample_rate,
                        "message": "Waiting for receiver audio. Recording and transcription continue.",
                    }
                )
                continue
            await websocket.send_bytes(chunk)
    except WebSocketDisconnect:
        return
    finally:
        receiver_manager.live_audio_hub.unsubscribe(int(repeater_id), queue)
