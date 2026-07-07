# CLAUDE.md

Guidance for working in this repo. Discord bot that monitors Bambu X1C 3D printers over their **local** MQTT broker and exposes status, camera snapshots, and error/pause alerts via slash commands. Lives on a local raspberry pi.

## Files

- `bot.py` — everything: MQTT client threads, printer state, Discord slash commands, camera snapshots, alert DMs.
- `config.py` — loads/validates `config.json`; writes an example config and exits on first run.
- `config.json` — secrets (Discord token, printer IP/serial/access_code). **Gitignored — never commit.**
- `subscribers.json` — DM alert subscriptions, `{ "all" | "<printer name>": [user_id, ...] }`. Written at runtime, gitignored.
- `error_codes.json` — maps Bambu error codes (`XXXX_XXXX` hex keys) to human descriptions. Loaded at startup.
- `bambu-discord.service` — systemd unit for the Pi (service name `bambu-discord`, runs as `pi`).
- `status.sh` — Pi-side helper wrapping `systemctl`/`journalctl` (status/logs/follow/restart/stop/start).
- `requirements.txt` — discord.py, paho-mqtt, requests, urllib3.

## Architecture

- **One MQTT thread per printer** (`PrinterMQTT`), daemon threads with auto-reconnect (10s backoff). Connects to `<ip>:8883` over TLS with `CERT_NONE` (printers use self-signed certs). Username is always `bblp`, password is the printer's access code. Subscribes to `device/<serial>/report`.
- **State** lives in `PrinterState` objects (one per printer) in the `printer_states` dict, keyed by printer name. `printer_cfgs` holds the raw config per name. MQTT threads mutate state; the Discord event loop reads it.
- **Cross-thread alerts:** MQTT threads fire `send_alert` back onto the bot's event loop via `asyncio.run_coroutine_threadsafe(..., bot_loop)`. `bot_loop` is captured in `on_ready`.
- **Snapshots:** `get_snapshot` shells out to **ffmpeg** to grab one JPEG frame from the RTSP stream `rtsps://bblp:<access_code>@<ip>:322/streaming/live/1`. `_find_ffmpeg()` locates the binary (PATH, then winget install dirs on Windows). Blocking, so it's run via `run_in_executor`.
- **MQTT payload parsing** is in `PrinterMQTT._parse`. Handles both new (`temperatures` dict) and older flat (`nozzle_temper`, etc.) firmware fields. `mc_remaining_time` is in **minutes** and converted to seconds. `gcode_state` maps to internal statuses: idle/running/paused/failed/finished.

## Alerts

- Fire on transition into `failed` or `paused`. `_alert_sent` guards against duplicate alerts until the status changes again.
- **Cancelled prints are suppressed** — `CANCEL_ERROR_CODES` (`0x0300400C`, `0x0500400E`) don't alert and clear the error message.
- Error codes are resolved via `resolve_error()` → `error_codes.json` using the `XXXX_XXXX` hex key format.

## Commands

- `/printers <name|number|list|all>` — `list` = one-line summary; `all` = full cards for every printer; otherwise matches by exact name or trailing number (`1` → `Printer 1`). `public:true` makes the reply non-ephemeral. Ephemeral by default.
- `/sub3d <subscribe|unsubscribe|status>` `[printer]` — manage DM alert subscriptions (per-printer or `all`).
- `/team <member>` — admin-only; grants the `Team Member` role (must exist; bot role must sit above it).
- `/update` — **owner-only**; `git pull` then `sudo systemctl restart bambu-discord`. Only works on the Pi deployment.

There is a per-`(guild, printer)` cooldown decorator on `/printers` that is **commented out** for testing (see `printers_cmd`). The error handler for it stays in place.

## Running

Dev (Windows): `venv\Scripts\Activate.ps1` then `python bot.py`. Requires ffmpeg (installed via winget `Gyan.FFmpeg`) and LAN access to the printers for MQTT + RTSP. First run without `config.json` generates an example and exits.

Deploy: Raspberry Pi via the systemd service; manage with `./status.sh`. Slash commands sync globally in `on_ready` (can take up to ~1h to propagate).

## Conventions / preferences

- The bot runs on a raspberry pi. do not run it locally on the dev machine. notify the user what to do for changes.
- Prefer concise command names (`/printers`, not `/status`).
- Cooldowns are per-printer, not global.
- Don't commit `config.json` or `subscribers.json`.

