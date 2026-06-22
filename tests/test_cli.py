from __future__ import annotations

from app.cli import build_parser


def test_config_argument_before_subcommand():
    args = build_parser().parse_args(["--config", "/tmp/rw.toml", "init-config"])

    assert args.config == "/tmp/rw.toml"
    assert args.command == "init-config"


def test_config_argument_after_subcommand():
    args = build_parser().parse_args(["init-config", "--config", "/tmp/rw.toml"])

    assert args.config == "/tmp/rw.toml"
    assert args.command == "init-config"


def test_serve_ssl_arguments():
    args = build_parser().parse_args(
        [
            "serve",
            "--config",
            "/tmp/rw.toml",
            "--ssl-certfile",
            "/etc/repeaterwatch/tls/server.crt",
            "--ssl-keyfile",
            "/etc/repeaterwatch/tls/server.key",
        ]
    )

    assert args.command == "serve"
    assert args.ssl_certfile == "/etc/repeaterwatch/tls/server.crt"
    assert args.ssl_keyfile == "/etc/repeaterwatch/tls/server.key"


def test_config_argument_before_serve_subcommand():
    args = build_parser().parse_args(["--config", "/etc/repeaterwatch/config.toml", "serve"])

    assert args.config == "/etc/repeaterwatch/config.toml"
    assert args.command == "serve"


def test_listen_sdr_command_parse():
    args = build_parser().parse_args(
        ["listen-sdr", "--config", "/tmp/rw.toml", "--frequency", "146.745M", "--squelch", "0", "--gain", "20"]
    )

    assert args.command == "listen-sdr"
    assert args.config == "/tmp/rw.toml"
    assert args.frequency == "146.745M"
    assert args.squelch == 0
    assert args.gain == "20"
