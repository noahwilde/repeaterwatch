# RepeaterWatch

RepeaterWatch is a local-first Raspberry Pi web app for monitoring analog FM repeaters with an RTL-SDR dongle. It records active transmissions, stores raw audio, transcribes recordings, generates rolling summaries, and sends standards-based Web Push notifications for keyword matches.

The UI is a plain FastAPI-served PWA, so there is no Node build step on the Pi.

## AI-Generated Code Notice

This project was built primarily with AI-generated code. It has automated tests and has been exercised on a local Raspberry Pi deployment, but it should still be reviewed carefully before relying on it for unattended or production use.

## Secrets And Local Data

Do not commit a live `config.toml`, `.env` file, VAPID private key, TLS private key, API key, SQLite database, or captured audio. The repository includes `config.example.toml` as a safe starting point, and `.gitignore` excludes local runtime config, keys, databases, recordings, caches, and build artifacts.

API credentials should be supplied through environment variables such as `OPENAI_API_KEY`. Web Push VAPID keys can be generated with `repeaterwatch generate-vapid`; keep the private key in `/etc/repeaterwatch/config.toml` or `REPEATERWATCH_VAPID_PRIVATE_KEY`, not in source control.

## Current Capabilities

- FastAPI backend with SQLite persistence.
- Static responsive PWA with manifest, service worker, iOS Home Screen onboarding, and notification subscription UI.
- Configurable repeater list from `config.toml` and the web UI, including inline edits for existing entries.
- Single-repeater `rtl_fm` receiver backend with crash restart and backoff.
- Shared RTL-SDR IQ receiver for multiple enabled repeaters that fit inside one usable passband.
- SDR window validation with center-frequency recommendations, guard bands, and per-repeater in-range status.
- Conservative PCM16 VOX segmenter with pre-roll, post-silence, minimum duration, and maximum split duration.
- WAV recording storage with metadata.
- Transcription worker with `noop`, `faster-whisper`, and OpenAI-compatible modes.
- Conservative summary worker with `noop`, OpenAI-compatible, and Ollama-compatible modes.
- Keyword phrase or regex rules with cooldowns and repeater filters.
- Web Push subscriptions and VAPID key generation.
- Retention cleanup that can delete raw audio while preserving metadata by default.

When one repeater is enabled, RepeaterWatch keeps the proven `rtl_fm` workflow. When multiple repeaters are enabled and `[sdr].multi_repeater_enabled = true`, it starts one `rtl_sdr` IQ source and channelizes each repeater in software. If the enabled repeaters do not fit inside the usable SDR passband, the receiver is not started and the UI shows the suggested center frequency and required sample rate.

## Install On Raspberry Pi OS

```bash
sudo apt update
sudo apt install -y rtl-sdr sox ffmpeg python3.13 python3.13-venv git
sudo useradd --system --create-home --groups plugdev repeaterwatch
sudo mkdir -p /opt/repeaterwatch /etc/repeaterwatch
```

Copy this project to `/opt/repeaterwatch`, then install it:

```bash
cd /opt/repeaterwatch
sudo rm -rf repeaterwatch.egg-info build dist
sudo chown -R repeaterwatch:repeaterwatch /opt/repeaterwatch /etc/repeaterwatch
sudo -u repeaterwatch python3.13 -m venv .venv
sudo -u repeaterwatch .venv/bin/pip install --upgrade pip
sudo -u repeaterwatch .venv/bin/pip install -e '.[transcribe]'
sudo -u repeaterwatch .venv/bin/repeaterwatch init-config --config /etc/repeaterwatch/config.toml
```

Generate Web Push keys and paste the printed `[notifications]` values into `/etc/repeaterwatch/config.toml`:

```bash
sudo -u repeaterwatch .venv/bin/repeaterwatch generate-vapid
```

Run it directly:

```bash
sudo -u repeaterwatch .venv/bin/repeaterwatch serve --config /etc/repeaterwatch/config.toml
```

Open `http://<pi-hostname>:8078`.

## HTTPS

Web Push requires a secure context. To serve RepeaterWatch directly over HTTPS, configure the server with a certificate and private key:

```toml
[server]
host = "0.0.0.0"
port = 8443
ssl_certfile = "/etc/repeaterwatch/tls/server.crt"
ssl_keyfile = "/etc/repeaterwatch/tls/server.key"
```

For a LAN-only install, generate a local CA and a server certificate with subject alternative names for the Pi IP address and hostname. Install and fully trust the local CA certificate on each iPhone/iPad before opening `https://<pi-hostname-or-ip>:8443`.

## systemd

```bash
sudo cp deploy/repeaterwatch.service /etc/systemd/system/repeaterwatch.service
sudo systemctl daemon-reload
sudo systemctl enable --now repeaterwatch
sudo journalctl -u repeaterwatch -f
```

The default service runs as user `repeaterwatch`, uses `/etc/repeaterwatch/config.toml`, and serves on `0.0.0.0:8078`.

## RTL-SDR Permissions

If the dongle is claimed by the DVB driver, blacklist it:

```bash
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl-sdr.conf
sudo reboot
```

For USB permissions, install the rtl-sdr udev rules from your distro package or copy the upstream rules for your dongle, then reload udev:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Test the receiver path:

```bash
repeaterwatch test-sdr --config /etc/repeaterwatch/config.toml --frequency 146.940M
```

Live listen while tuning squelch:

```bash
sudo -u repeaterwatch .venv/bin/repeaterwatch listen-sdr \
  --config /etc/repeaterwatch/config.toml \
  --frequency 146.745M \
  --gain 20 \
  --squelch 0
```

Use `--squelch 0` to hear the raw noise floor first, then raise squelch until idle noise stops. Try `--squelch 40`, `60`, `80`, and `100`. If squelch has to be very high, try lower fixed gain values such as `--gain 10` or `--gain 20` instead of `auto`.

The web UI also includes **Live Squelch Test**, which plays a temporary receiver stream in the browser and shows the level RepeaterWatch uses for VOX decisions. Normal RepeaterWatch receivers are paused while the live web test is active, then resumed when it stops.

## Multi-Repeater Monitoring

RepeaterWatch can monitor multiple enabled repeaters from one RTL-SDR when their receive frequencies fit inside the configured SDR sample rate after guard bands.

Recommended defaults:

```toml
[sdr]
multi_repeater_enabled = true
sample_rate = 2400000
guard_band_khz = 100
edge_warning_khz = 50
# Optional fixed center. When omitted, RepeaterWatch uses the midpoint of enabled repeaters.
# center_frequency_mhz = 146.8725
```

The usable passband is:

```text
sample_rate - (2 * guard_band)
```

With the default `2400000` Hz sample rate and `100` kHz guard band, the usable bandwidth is about `2.2` MHz. Disabled repeaters do not affect the center-frequency calculation or validation.

New repeater config files may use either legacy or descriptive field names:

```toml
[[repeaters]]
name = "Local 2m Repeater"
frequency_mhz = 146.745
tone = "100.0"
enabled = true

[[repeaters]]
name = "Regional Weather Net"
receive_frequency = 147.210
location = "Example Region"
coverage_area = "Regional"
repeater_type = "weather"
enabled = true
```

The Radio tab shows the current SDR center frequency, sample rate, usable edges, and repeater markers:

- Green: inside the usable passband.
- Yellow: near the guard-band edge.
- Red: outside the usable passband.
- Gray: disabled.

If a repeater is outside the current window, either disable it, increase `[sdr].sample_rate` within RTL-SDR limits, or set a different `[sdr].center_frequency_mhz`. RepeaterWatch suggests the midpoint center frequency but does not rewrite it automatically.

Known limitations:

- The shared receiver uses a lightweight NumPy NBFM channelizer intended for Raspberry Pi-class hardware. Start with a few nearby repeaters and watch CPU/load.
- Very weak signals near the passband edge may need a higher sample rate, lower guard band only if RF conditions allow, or a better antenna/filter.
- One RTL-SDR cannot monitor frequencies that exceed its usable instantaneous bandwidth.

## Recording Segmentation

RepeaterWatch keeps a recording open until VOX sees `post_silence_seconds` of quiet audio. The default is `6.0` seconds, so short pauses, repeater courtesy tones, and squelch tails stay attached to the preceding transmission instead of creating separate beep-only recordings.

## Transcription

Default transcription mode is `noop`, which preserves the workflow without running speech-to-text. For local transcription:

```toml
[transcription]
backend = "faster-whisper"
model = "base"
compute_type = "int8"
```

Larger Whisper models improve accuracy but are slower on Raspberry Pi hardware. Ham callsigns may still be misrecognized; RepeaterWatch stores the original transcript and supports corrections from the API/UI path.

OpenAI-compatible transcription can be configured with:

```toml
[transcription]
backend = "openai-compatible"
remote_base_url = "https://api.openai.com/v1"
remote_api_key_env = "OPENAI_API_KEY"
remote_model = "gpt-4o-transcribe"
```

RepeaterWatch sends the repeater name, frequency, tone, optional location, coverage area, type, notes, and known repeater callsign as transcription context. For OpenAI-compatible transcription, it also applies a voice-band cleanup pass with `ffmpeg` before upload when `ffmpeg` is available. This improves automated repeater IDs and helps the transcript mark static-only or unintelligible recordings conservatively.

## Summaries

Default summary mode is `noop`, which creates a local extractive summary and never invents callsigns. For Ollama:

```toml
[summary]
backend = "ollama"
base_url = "http://localhost:11434"
model = "llama3.1"
```

For an OpenAI-compatible chat API:

```toml
[summary]
backend = "openai-compatible"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
model = "gpt-4.1-mini"
```

AI summaries receive trusted receiver context for each transcript, including repeater name, frequency, tone, optional location, coverage area, type, and notes. Combined summaries preserve the source repeater metadata for each transcript and should not merge unrelated traffic unless the transcripts clearly support correlation.

## iOS Web Push

iOS/iPadOS Web Push requires all of these:

- iOS/iPadOS 16.4 or newer.
- An HTTPS URL with a trusted certificate. Plain LAN HTTP such as `http://<pi-hostname-or-ip>:8078` is not a secure context, so iOS will not expose Service Worker/Web Push APIs.
- A Home Screen web app. Open the HTTPS URL in Safari, use Share > Add to Home Screen, then reopen RepeaterWatch from the Home Screen icon before enabling notifications.

The permission request is only made after the user presses the enable button.

References:

- [Apple: Sending web push notifications in web apps and browsers](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers)
- [WebKit: Web Push for Web Apps on iOS and iPadOS](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)

Web Push usually requires HTTPS except for localhost. For LAN HTTPS, install Caddy and adapt `deploy/Caddyfile.example`.

## CLI

```bash
repeaterwatch serve --config config.toml
repeaterwatch init-config --config config.toml
repeaterwatch generate-vapid
repeaterwatch test-sdr --config config.toml --frequency 146.940M
repeaterwatch listen-sdr --config config.toml --frequency 146.745M --squelch 0
repeaterwatch transcribe-pending --config config.toml
repeaterwatch summarize-now --config config.toml --window last_hour
repeaterwatch cleanup --config config.toml --days 30
```

## Updating An Existing Pi Install

After copying updated project files to `/opt/repeaterwatch`:

```bash
cd /opt/repeaterwatch
sudo systemctl stop repeaterwatch
sudo rm -rf repeaterwatch.egg-info build dist
sudo chown -R repeaterwatch:repeaterwatch /opt/repeaterwatch /etc/repeaterwatch
sudo -u repeaterwatch .venv/bin/pip install -e '.[transcribe]'
sudo systemctl start repeaterwatch
sudo journalctl -u repeaterwatch -f
```

## Safety And Legal Notice

You are responsible for complying with local laws, radio regulations, license terms, and privacy rules. RepeaterWatch is intended only for transmissions you are legally allowed to receive and store.
