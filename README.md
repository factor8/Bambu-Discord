# Bambu X1C Discord Bot

Discord bot that lets you query live status + camera snapshots from your Bambu X1C printers via slash commands, with automatic alerts for errors and pauses.

## Commands

| Command | Description |
|---|---|
| `/status` | Shows all printers with live data + snapshot |
| `/status printer-1` | Shows a specific printer |
| `/printers` | Lists all printers and connection state |

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

### 3. Get Your Alert Channel ID

In Discord: Enable Developer Mode (Settings → Advanced), right-click your target channel → **Copy ID**

### 4. Install on Raspberry Pi

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

### 5. Fill In config.json

```json
{
  "discord_token": "your-bot-token",
  "alert_channel_id": 1234567890123456789,
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

### 6. Run It

```bash
source venv/bin/activate
python bot.py
```

### 7. Install as a Service (auto-start on boot)

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
- Camera snapshots use the printer's local HTTP endpoint
- Alerts fire automatically for **pause** and **error/failed** states
- The Pi must be on the same local network as the printers

## Troubleshooting

**Bot connects but no MQTT data**: Double-check your serial number and access code. The serial is case-sensitive.

**Snapshots fail**: Some firmware versions require the printer to be actively printing. Try `/status` during a print.

**Slash commands don't appear**: It can take up to 1 hour for Discord to propagate global slash commands. For instant registration, use guild-specific commands (add your server ID to the sync call).
