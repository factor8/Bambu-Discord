import json
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

EXAMPLE_CONFIG = {
    "discord_token": "YOUR_DISCORD_BOT_TOKEN_HERE",
    "printers": [
        {
            "name": "Printer 1",
            "ip": "192.168.1.100",
            "serial": "YOUR_PRINTER_SERIAL",
            "access_code": "YOUR_ACCESS_CODE"
        },
        {
            "name": "Printer 2",
            "ip": "192.168.1.101",
            "serial": "YOUR_PRINTER_SERIAL_2",
            "access_code": "YOUR_ACCESS_CODE_2"
        }
    ]
}


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w") as f:
            json.dump(EXAMPLE_CONFIG, f, indent=2)
        print(f"Created example config at {CONFIG_PATH}")
        print("Please fill in your printer details and Discord token, then re-run.")
        sys.exit(0)

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    # Validate
    required = ["discord_token", "printers"]
    for key in required:
        if key not in cfg:
            print(f"Missing required config key: {key}")
            sys.exit(1)

    for p in cfg["printers"]:
        for field in ["name", "ip", "serial", "access_code"]:
            if field not in p:
                print(f"Printer config missing field: {field}")
                sys.exit(1)

    return cfg
