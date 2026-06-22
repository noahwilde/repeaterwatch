from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

import uvicorn

from app.config import AppConfig, default_config, load_config, save_config
from app.db import Database
from app.notify.webpush import KeywordEngine, NotificationService, generate_vapid_keys
from app.retention import cleanup_retention
from app.sdr.rtl_fm import build_rtl_fm_command
from app.summarize.llm import SummaryService
from app.transcribe.whisper import TranscriptionWorker


def _load_runtime(config_path: Path) -> tuple[AppConfig, Database, Path]:
    config = load_config(config_path)
    data_dir = config.storage.resolved_data_dir(config_path)
    db = Database(data_dir / "repeaterwatch.sqlite3")
    db.seed_repeaters(config.repeaters)
    return config, db, data_dir


def serve(args: argparse.Namespace) -> None:
    config_path = Path(args.config).expanduser().resolve()
    os.environ["REPEATERWATCH_CONFIG"] = str(config_path)
    config = load_config(config_path)
    ssl_certfile = args.ssl_certfile or config.server.ssl_certfile
    ssl_keyfile = args.ssl_keyfile or config.server.ssl_keyfile
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=args.host or config.server.host,
        port=args.port or config.server.port,
        reload=args.reload,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
        app_dir=str(Path.cwd()),
    )


def init_config(args: argparse.Namespace) -> None:
    path = Path(args.config).expanduser()
    if path.exists() and not args.force:
        raise SystemExit(f"{path} already exists. Use --force to overwrite.")
    save_config(default_config(), path)
    print(f"Wrote {path}")


def generate_vapid(_: argparse.Namespace) -> None:
    keys = generate_vapid_keys()
    print("[notifications]")
    print(f'vapid_public_key = "{keys["public_key"]}"')
    escaped_private = keys["private_key"].replace("\\", "\\\\").replace("\n", "\\n")
    print(f'vapid_private_key = "{escaped_private}"')
    print('subject = "mailto:admin@example.local"')


def test_sdr(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    frequency = args.frequency.rstrip("M").rstrip("m")
    repeater = {
        "name": "test",
        "frequency_mhz": float(frequency),
        "squelch_level": args.squelch,
        "sample_rate": args.sample_rate,
        "gain": args.gain,
        "ppm": args.ppm,
    }
    command = build_rtl_fm_command(repeater, config)
    print("Running: " + " ".join(command))
    try:
        subprocess.run(command, timeout=args.seconds, check=False)
    except FileNotFoundError:
        raise SystemExit("rtl_fm was not found in PATH. Install rtl-sdr.")
    except subprocess.TimeoutExpired:
        print("SDR test completed.")


def listen_sdr(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    frequency = args.frequency.rstrip("M").rstrip("m")
    sample_rate = args.sample_rate
    repeater = {
        "name": "live-listen",
        "frequency_mhz": float(frequency),
        "squelch_level": args.squelch,
        "sample_rate": sample_rate,
        "gain": args.gain,
        "ppm": args.ppm,
    }
    command = build_rtl_fm_command(repeater, config)
    player = None
    if shutil.which("play"):
        player = ["play", "-q", "-t", "raw", "-r", str(sample_rate), "-e", "signed", "-b", "16", "-c", "1", "-"]
    elif shutil.which("ffplay"):
        player = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "warning", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0"]
    if player is None:
        raise SystemExit("No audio player found. Install sox or ffmpeg for play/ffplay.")

    print("Running: " + " ".join(command))
    print("Player: " + " ".join(player))
    rtl_process: subprocess.Popen[bytes] | None = None
    player_process: subprocess.Popen[bytes] | None = None
    try:
        rtl_process = subprocess.Popen(command, stdout=subprocess.PIPE)
        assert rtl_process.stdout is not None
        player_process = subprocess.Popen(player, stdin=rtl_process.stdout)
        rtl_process.stdout.close()
        player_process.wait()
    except FileNotFoundError:
        raise SystemExit("rtl_fm was not found in PATH. Install rtl-sdr.")
    except KeyboardInterrupt:
        print("\nStopping live listener.")
    finally:
        for process in (player_process, rtl_process):
            if process and process.poll() is None:
                process.terminate()


async def transcribe_pending(args: argparse.Namespace) -> None:
    config, db, _ = _load_runtime(Path(args.config).expanduser().resolve())
    try:
        notification_service = NotificationService(db, config)
        keyword_engine = KeywordEngine(db, notification_service)
        worker = TranscriptionWorker(db, config, keyword_engine)
        count = await worker.process_pending(args.limit)
        print(f"Processed {count} pending recording(s).")
    finally:
        db.close()


async def summarize_now(args: argparse.Namespace) -> None:
    config, db, _ = _load_runtime(Path(args.config).expanduser().resolve())
    try:
        service = SummaryService(db, config)
        summary_id = await service.generate(args.window, args.repeater_id)
        print(f"Created summary {summary_id}.")
    finally:
        db.close()


def cleanup(args: argparse.Namespace) -> None:
    config, db, _ = _load_runtime(Path(args.config).expanduser().resolve())
    try:
        if args.days:
            config.retention.raw_audio_days = args.days
        report = cleanup_retention(db, config)
        print(
            f"Deleted {report.audio_deleted} audio file(s), "
            f"{report.transcripts_deleted} transcript(s), "
            f"{report.summaries_deleted} summary row(s)."
        )
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repeaterwatch")
    parser.add_argument("--config", default="config.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--config", default=argparse.SUPPRESS)
    serve_parser.add_argument("--host")
    serve_parser.add_argument("--port", type=int)
    serve_parser.add_argument("--ssl-certfile")
    serve_parser.add_argument("--ssl-keyfile")
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.set_defaults(func=serve)

    init_parser = subparsers.add_parser("init-config")
    init_parser.add_argument("--config", default=argparse.SUPPRESS)
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=init_config)

    vapid_parser = subparsers.add_parser("generate-vapid")
    vapid_parser.add_argument("--config", default=argparse.SUPPRESS)
    vapid_parser.set_defaults(func=generate_vapid)

    sdr_parser = subparsers.add_parser("test-sdr")
    sdr_parser.add_argument("--config", default=argparse.SUPPRESS)
    sdr_parser.add_argument("--frequency", required=True, help="Frequency such as 146.940M")
    sdr_parser.add_argument("--seconds", type=int, default=10)
    sdr_parser.add_argument("--squelch", type=int, default=50)
    sdr_parser.add_argument("--sample-rate", type=int, default=24_000)
    sdr_parser.add_argument("--gain", default="auto")
    sdr_parser.add_argument("--ppm", type=int, default=0)
    sdr_parser.set_defaults(func=test_sdr)

    listen_parser = subparsers.add_parser("listen-sdr")
    listen_parser.add_argument("--config", default=argparse.SUPPRESS)
    listen_parser.add_argument("--frequency", required=True, help="Frequency such as 146.745M")
    listen_parser.add_argument("--squelch", type=int, default=0)
    listen_parser.add_argument("--sample-rate", type=int, default=24_000)
    listen_parser.add_argument("--gain", default="auto")
    listen_parser.add_argument("--ppm", type=int, default=0)
    listen_parser.set_defaults(func=listen_sdr)

    transcribe_parser = subparsers.add_parser("transcribe-pending")
    transcribe_parser.add_argument("--config", default=argparse.SUPPRESS)
    transcribe_parser.add_argument("--limit", type=int, default=10)
    transcribe_parser.set_defaults(func=lambda args: asyncio.run(transcribe_pending(args)))

    summarize_parser = subparsers.add_parser("summarize-now")
    summarize_parser.add_argument("--config", default=argparse.SUPPRESS)
    summarize_parser.add_argument(
        "--window",
        default="quarter_hour",
        choices=["quarter_hour", "hour", "day", "last_15_minutes", "last_hour", "today"],
    )
    summarize_parser.add_argument("--repeater-id", type=int)
    summarize_parser.set_defaults(func=lambda args: asyncio.run(summarize_now(args)))

    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--config", default=argparse.SUPPRESS)
    cleanup_parser.add_argument("--days", type=int, help="Override raw audio retention days for this run")
    cleanup_parser.set_defaults(func=cleanup)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
