# Bambu X1C Discord Bot

Discord bot that lets you query live status + camera snapshots from your Bambu X1C printers via slash commands, with automatic alerts for errors and pauses.

## Commands

| Command | Description |
|---|---|
| `/printers list` | One-line summary of all printers and connection state |
| `/printers all` | Full status cards with snapshots for every printer |
| `/printers <name or number>` | Full status card with snapshot for a specific printer (e.g. `/printers 1` or `/printers Printer 1`) |
| `/sub3d subscribe` | Subscribe to DM notifications for all printers |
| `/sub3d subscribe printer:<name>` | Subscribe to DM notifications for a specific printer |
| `/sub3d unsubscribe` | Unsubscribe from all printer notifications |
| `/sub3d unsubscribe printer:<name>` | Unsubscribe from a specific printer |
| `/sub3d status` | Show your current subscriptions |
| `/update` | (Owner only) Git pull and restart the bot |

All commands are **ephemeral** (only visible to you) by default. Use the `public` option on `/printers` to show the response to everyone.

## Setup

### 1. Create a Discord Bot

1. Go to https://discord.com/developers/applications → **New Application**
2. Go to **Bot** → **Add Bot** → copy the **Token**
3. Under **Privileged Gateway Intents**, enable **Message Content Intent**
4. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Attach Files`, `Embed Links`, `Use Slash Commands`
5. Open the generated URL to invite the bot to your server

### 2. Get Your Printer Credentials

On the printer touchscreen:
- **IP Address**: Settings → Network → IP Address
- **Serial Number**: Settings → Device → Serial Number  
- **Access Code**: Settings → Network → Access Code (8-character code)

### 3. Install on Raspberry Pi

```bash
# Clone / copy files to your Pi
mkdir ~/bambu-discord-bot
cd ~/bambu-discord-bot
# copy bot.py, config.py, requirements.txt here

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# First run generates config.json
python bot.py
```

### 4. Fill In config.json

```json
{
  "discord_token": "your-bot-token",
  "printers": [
    {
      "name": "Printer 1",
      "ip": "192.168.1.100",
      "serial": "01P00A...",
      "access_code": "12345678"
    }
  ]
}
```

### 5. Run It

```bash
source venv/bin/activate
python bot.py
```

### 6. Install as a Service (auto-start on boot)

```bash
sudo cp bambu-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bambu-bot
sudo systemctl start bambu-bot

# Check logs
sudo journalctl -u bambu-bot -f
```

## Notes

- The bot connects to each printer's **local MQTT broker** (port 8883) — no cloud required
- Camera snapshots use the printer's local RTSP stream via ffmpeg
- Alerts are sent as DMs to subscribed users (use `/sub3d`) for **pause** and **error/failed** states
- The Pi must be on the same local network as the printers

## Troubleshooting

**Bot connects but no MQTT data**: Double-check your serial number and access code. The serial is case-sensitive.

**Snapshots fail**: Some firmware versions require the printer to be actively printing. Try `/status` during a print.

**Slash commands don't appear**: It can take up to 1 hour for Discord to propagate global slash commands. For instant registration, use guild-specific commands (add your server ID to the sync call).
