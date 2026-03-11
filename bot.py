import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import ssl
import threading
import os
import time
import io
import subprocess
import tempfile
from datetime import datetime
from typing import Optional
import paho.mqtt.client as mqtt

from config import load_config

# ─── Error Code Lookup ────────────────────────────────────────────────────────

_error_codes = {}

def _load_error_codes():
    global _error_codes
    codes_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error_codes.json")
    try:
        with open(codes_path, "r") as f:
            _error_codes = json.load(f)
        print(f"Loaded {len(_error_codes)} error codes")
    except Exception as e:
        print(f"Warning: Could not load error_codes.json: {e}")

# Cancel error codes (decimal values) — these should not trigger alerts
CANCEL_ERROR_CODES = {
    0x0300400C,  # MC: Printing was cancelled
    0x0500400E,  # System: Printing was cancelled
}

def resolve_error(error_code: int) -> str:
    """Convert a numeric error code to a human-readable description."""
    error_hex = f"{error_code:08X}"
    error_key = f"{error_hex[:4]}_{error_hex[4:]}"
    description = _error_codes.get(error_key)
    if description:
        return f"{description} (`{error_key}`)"
    return f"Unknown error `{error_key}`"

# ─── Printer State Store ──────────────────────────────────────────────────────

class PrinterState:
    def __init__(self, name: str):
        self.name = name
        self.connected = False
        self.print_status = "idle"       # idle, running, paused, failed, finished
        self.current_file = None
        self.progress = 0
        self.time_remaining = 0          # seconds
        self.layer_current = 0
        self.layer_total = 0
        self.nozzle_temp = 0.0
        self.bed_temp = 0.0
        self.chamber_temp = 0.0
        self.last_updated = None
        self.error_message = None
        self._alert_sent = False         # prevent duplicate alerts

    def to_embed_fields(self):
        fields = []

        status_emoji = {
            "idle": "⬜",
            "running": "🟢",
            "paused": "🟡",
            "failed": "🔴",
            "finished": "✅",
        }.get(self.print_status, "❓")

        fields.append(("Status", f"{status_emoji} {self.print_status.capitalize()}", True))

        if self.current_file:
            fields.append(("File", f"`{self.current_file}`", True))

        if self.print_status in ("running", "paused", "finished"):
            fields.append(("Progress", f"{self.progress}%", True))

            if self.layer_total > 0:
                fields.append(("Layers", f"{self.layer_current} / {self.layer_total}", True))

            if self.time_remaining > 0:
                mins = self.time_remaining // 60
                hrs, mins = divmod(mins, 60)
                time_str = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"
                fields.append(("Time Left", time_str, True))

        fields.append(("Nozzle", f"{self.nozzle_temp:.1f}°C", True))
        fields.append(("Bed", f"{self.bed_temp:.1f}°C", True))

        if self.error_message:
            fields.append(("⚠️ Error", self.error_message, False))

        if self.last_updated:
            fields.append(("Last Updated", f"<t:{int(self.last_updated.timestamp())}:R>", False))

        return fields


# ─── MQTT Manager ─────────────────────────────────────────────────────────────

class PrinterMQTT:
    def __init__(self, printer_cfg: dict, state: PrinterState, alert_callback):
        self.cfg = printer_cfg
        self.state = state
        self.alert_callback = alert_callback
        self.client = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        serial = self.cfg["serial"]
        username = "bblp"
        password = self.cfg["access_code"]
        host = self.cfg["ip"]

        client = mqtt.Client(client_id=f"bambu_discord_{serial}", protocol=mqtt.MQTTv311)
        client.username_pw_set(username, password)

        tls_ctx = ssl.create_default_context()
        tls_ctx.check_hostname = False
        tls_ctx.verify_mode = ssl.CERT_NONE
        client.tls_set_context(tls_ctx)

        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect

        self.client = client

        while True:
            try:
                client.connect(host, 8883, keepalive=60)
                client.loop_forever()
            except Exception as e:
                print(f"[{self.state.name}] MQTT connection error: {e}")
                self.state.connected = False
                time.sleep(10)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            serial = self.cfg["serial"]
            client.subscribe(f"device/{serial}/report")
            self.state.connected = True
            print(f"[{self.state.name}] Connected to MQTT")
        else:
            print(f"[{self.state.name}] MQTT connect failed rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.state.connected = False
        print(f"[{self.state.name}] MQTT disconnected rc={rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self._parse(payload)
        except Exception as e:
            print(f"[{self.state.name}] Parse error: {e}")

    def _parse(self, payload: dict):
        s = self.state
        prev_status = s.print_status

        # Print status
        if "print" in payload:
            p = payload["print"]

            gcode_state = p.get("gcode_state", "").lower()
            if gcode_state:
                s.print_status = {
                    "idle": "idle",
                    "running": "running",
                    "pause": "paused",
                    "failed": "failed",
                    "finish": "finished",
                }.get(gcode_state, gcode_state)

            s.progress = p.get("mc_percent", s.progress)
            s.time_remaining = p.get("mc_remaining_time", s.time_remaining) * 60  # minutes -> seconds
            s.layer_current = p.get("layer_num", s.layer_current)
            s.layer_total = p.get("total_layer_num", s.layer_total)
            s.last_updated = datetime.now()

            # File name
            subtask = p.get("subtask_name")
            if subtask:
                s.current_file = subtask

            # Temperatures
            temps = p.get("temperatures", {})
            if not temps:
                # older firmware flat fields
                s.nozzle_temp = p.get("nozzle_temper", s.nozzle_temp)
                s.bed_temp = p.get("bed_temper", s.bed_temp)
                s.chamber_temp = p.get("chamber_temper", s.chamber_temp)
            else:
                s.nozzle_temp = temps.get("nozzle", s.nozzle_temp)
                s.bed_temp = temps.get("bed", s.bed_temp)
                s.chamber_temp = temps.get("chamber", s.chamber_temp)

            # Error detection
            error_code = p.get("print_error", 0)
            is_cancel = error_code in CANCEL_ERROR_CODES
            if error_code and error_code != 0 and not is_cancel:
                s.error_message = resolve_error(error_code)
            elif is_cancel:
                s.error_message = None
            elif s.print_status not in ("failed",):
                s.error_message = None

        # Fire alerts (skip cancelled prints)
        if s.print_status != prev_status:
            s._alert_sent = False

        if s.print_status in ("failed", "paused") and not s._alert_sent:
            # Don't alert for cancelled prints
            error_code = payload.get("print", {}).get("print_error", 0)
            if error_code in CANCEL_ERROR_CODES:
                s._alert_sent = True  # suppress alert
            else:
                s._alert_sent = True
                asyncio.run_coroutine_threadsafe(
                    self.alert_callback(s),
                    bot_loop
                )


# ─── Camera Snapshot ──────────────────────────────────────────────────────────

def _find_ffmpeg() -> str:
    """Locate the ffmpeg executable."""
    import shutil
    path = shutil.which("ffmpeg")
    if path:
        return path
    # Check common winget install location
    winget_base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    if os.path.isdir(winget_base):
        for d in os.listdir(winget_base):
            if "FFmpeg" in d:
                candidate = os.path.join(winget_base, d)
                for root, dirs, files in os.walk(candidate):
                    if "ffmpeg.exe" in files:
                        return os.path.join(root, "ffmpeg.exe")
    return "ffmpeg"  # fallback, hope it's on PATH

FFMPEG_PATH = _find_ffmpeg()


def get_snapshot(printer_cfg: dict) -> Optional[bytes]:
    """Grab a JPEG snapshot from the printer's RTSP stream via ffmpeg."""
    ip = printer_cfg["ip"]
    access_code = printer_cfg["access_code"]

    rtsp_url = f"rtsps://bblp:{access_code}@{ip}:322/streaming/live/1"
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        result = subprocess.run(
            [
                FFMPEG_PATH, "-y",
                "-rtsp_transport", "tcp",
                "-i", rtsp_url,
                "-frames:v", "1",
                "-q:v", "2",
                tmp_path,
            ],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            with open(tmp_path, "rb") as f:
                return f.read()
        else:
            print(f"Snapshot ffmpeg error for {ip}: {result.stderr.decode()[-200:]}")
    except subprocess.TimeoutExpired:
        print(f"Snapshot timeout for {ip}")
    except Exception as e:
        print(f"Snapshot error for {ip}: {e}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    return None


# ─── Bot Setup ────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
bot_loop = None

printer_states: dict[str, PrinterState] = {}
printer_cfgs: dict[str, dict] = {}
alert_channel_id: int = None


async def send_alert(state: PrinterState):
    """Auto-post alert to configured channel."""
    if not alert_channel_id:
        return
    channel = bot.get_channel(alert_channel_id)
    if not channel:
        return

    emoji = "🟡" if state.print_status == "paused" else "🔴"
    label = "Paused" if state.print_status == "paused" else "Failed / Error"

    embed = discord.Embed(
        title=f"{emoji} {state.name} — {label}",
        color=discord.Color.yellow() if state.print_status == "paused" else discord.Color.red(),
        timestamp=datetime.now()
    )
    if state.current_file:
        embed.add_field(name="File", value=f"`{state.current_file}`", inline=True)
    embed.add_field(name="Progress", value=f"{state.progress}%", inline=True)
    if state.error_message:
        embed.add_field(name="Error", value=state.error_message, inline=False)

    # Attach snapshot if available
    cfg = printer_cfgs.get(state.name)
    file_obj = None
    if cfg:
        img = await asyncio.get_event_loop().run_in_executor(None, get_snapshot, cfg)
        if img:
            file_obj = discord.File(io.BytesIO(img), filename="snapshot.jpg")
            embed.set_image(url="attachment://snapshot.jpg")

    await channel.send(
        content=f"@here **{state.name}** needs attention!",
        embed=embed,
        file=file_obj
    )


def build_status_embed(name: str, state: PrinterState, include_image: bool) -> tuple[discord.Embed, Optional[bytes]]:
    color_map = {
        "idle": discord.Color.light_grey(),
        "running": discord.Color.green(),
        "paused": discord.Color.yellow(),
        "failed": discord.Color.red(),
        "finished": discord.Color.blue(),
    }
    color = color_map.get(state.print_status, discord.Color.default())

    if not state.connected:
        embed = discord.Embed(title=f"🔌 {name} — Offline", color=discord.Color.dark_grey())
        return embed, None

    embed = discord.Embed(title=f"🖨️ {name}", color=color, timestamp=datetime.now())
    for fname, fval, inline in state.to_embed_fields():
        embed.add_field(name=fname, value=fval, inline=inline)

    img_data = None
    if include_image:
        cfg = printer_cfgs.get(name)
        if cfg:
            img_data = get_snapshot(cfg)
            if img_data:
                fname = f"snapshot_{name.replace(' ', '_')}.jpg"
                embed.set_image(url=f"attachment://{fname}")

    embed.set_footer(text="Bambu X1C Monitor")
    return embed, img_data


@bot.event
async def on_ready():
    global bot_loop
    bot_loop = asyncio.get_event_loop()
    print(f"Bot ready: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Sync error: {e}")


@bot.tree.command(name="printers", description="Get detailed status for a specific printer")
# @app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id, (i.namespace.printer or "").lower()))
@app_commands.describe(printer="Printer name or number (e.g. 1, 2)", public="Show the response to everyone")
async def printers_cmd(interaction: discord.Interaction, printer: str, public: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=not public)

    key = printer.strip().lower()

    if key == "list":
        lines = []
        for name, state in printer_states.items():
            dot = "🟢" if state.connected else "🔴"
            lines.append(f"{dot} **{name}** — {state.print_status}")
        await interaction.followup.send("\n".join(lines) if lines else "No printers configured.")
        return

    # "all" shows full cards for every printer
    if key == "all":
        targets = printer_states
    else:
        # Match by full name or just the number (e.g. "1" matches "Printer 1")
        match = next((k for k in printer_states if k.lower() == key), None)
        if not match:
            match = next((k for k in printer_states if k.lower().endswith(f" {key}") or k.lower().startswith(f"{key} ")), None)
        if not match:
            await interaction.followup.send(
                f"❌ Unknown printer `{printer}`. Available: {', '.join(f'`{k}`' for k in printer_states)}",
                ephemeral=True
            )
            return
        targets = {match: printer_states[match]}

    embeds = []
    files = []
    for name, state in targets.items():
        embed, img_data = await asyncio.get_event_loop().run_in_executor(
            None, build_status_embed, name, state, True
        )
        if img_data:
            fname = f"snapshot_{name.replace(' ', '_')}.jpg"
            files.append(discord.File(io.BytesIO(img_data), filename=fname))
        embeds.append(embed)

    await interaction.followup.send(embeds=embeds, files=files if files else discord.utils.MISSING)


@bot.tree.command(name="update", description="Pull latest code from GitHub and restart the bot")
async def update_cmd(interaction: discord.Interaction):
    if interaction.user.id != (await bot.application_info()).owner.id:
        await interaction.response.send_message("Only the bot owner can do this.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True, ephemeral=True)

    # Git pull
    try:
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        output = result.stdout.strip() or result.stderr.strip() or "No output"
    except Exception as e:
        await interaction.followup.send(f"Git pull failed: {e}")
        return

    await interaction.followup.send(f"**Git pull:**\n```\n{output}\n```\nRestarting bot...")

    # Restart via systemd (this kills the current process, systemd brings it back)
    await asyncio.sleep(1)
    os.system("sudo systemctl restart bambu-discord")


@printers_cmd.error
async def printers_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"Please wait {error.retry_after:.0f}s before using `/printers` again.",
            ephemeral=True
        )
    else:
        raise error


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    global alert_channel_id

    _load_error_codes()
    cfg = load_config()
    alert_channel_id = cfg.get("alert_channel_id")

    for p in cfg["printers"]:
        name = p["name"]
        state = PrinterState(name)
        printer_states[name] = state
        printer_cfgs[name] = p

        mqtt_mgr = PrinterMQTT(p, state, send_alert)
        mqtt_mgr.start()

    bot.run(cfg["discord_token"])


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()
