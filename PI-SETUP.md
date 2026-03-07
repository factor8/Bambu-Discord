# Raspberry Pi Setup

## 1. Install dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg git
```

## 2. Clone the repo

```bash
cd ~
git clone https://github.com/YOUR_USERNAME/Bambu-Discord.git
cd Bambu-Discord
```

## 3. Create venv and install packages

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 4. Add your config

Copy your `config.json` into `~/Bambu-Discord/`. Make sure printer IPs are correct for the Pi's network.

## 5. Create the systemd service

```bash
sudo nano /etc/systemd/system/bambu-discord.service
```

Paste the following (replace `pi` with your username if different — check with `whoami`):

```ini
[Unit]
Description=Bambu Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Bambu-Discord
ExecStart=/home/pi/Bambu-Discord/venv/bin/python bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

## 6. Allow the `/update` command to restart the bot

The bot's `/update` Discord command runs `sudo systemctl restart bambu-discord`. For this to work without a password prompt, add a sudoers rule:

```bash
sudo visudo -f /etc/sudoers.d/bambu-bot
```

Add this line (replace `pi` with your username):

```
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart bambu-discord
```

Save and exit (`Ctrl+X`, then `Y`, then `Enter`).

## 7. Enable and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable bambu-discord
sudo systemctl start bambu-discord
```

---

## Handy commands

| Command | What it does |
|---|---|
| `sudo systemctl start bambu-discord` | Start the bot |
| `sudo systemctl stop bambu-discord` | Stop the bot |
| `sudo systemctl restart bambu-discord` | Restart the bot |
| `sudo systemctl status bambu-discord` | Check if it's running |
| `sudo journalctl -u bambu-discord -f` | Live log output (Ctrl+C to exit) |
| `sudo journalctl -u bambu-discord --since "1 hour ago"` | Recent logs |

## Updating manually (without the Discord command)

```bash
cd ~/Bambu-Discord
git pull
sudo systemctl restart bambu-discord
```
