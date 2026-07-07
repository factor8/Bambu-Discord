#!/bin/bash
# Usage: ./status.sh [logs|restart|stop|start]

SERVICE="bambu-discord"

if ! systemctl list-unit-files --type=service 2>/dev/null | grep -q "^${SERVICE}.service"; then
  echo "Service '${SERVICE}' is not installed. To install it, run:"
  echo "  sudo cp $(dirname "$0")/bambu-discord.service /etc/systemd/system/"
  echo "  sudo systemctl daemon-reload"
  echo "  sudo systemctl enable ${SERVICE}"
  echo "  sudo systemctl start ${SERVICE}"
  exit 1
fi

case "${1:-status}" in
  status)
    systemctl status "$SERVICE"
    ;;
  logs)
    journalctl -u "$SERVICE" -n ${2:-50} --no-pager
    ;;
  follow)
    journalctl -u "$SERVICE" -f
    ;;
  restart)
    sudo systemctl restart "$SERVICE" && echo "Restarted $SERVICE" && systemctl status "$SERVICE"
    ;;
  stop)
    sudo systemctl stop "$SERVICE" && echo "Stopped $SERVICE"
    ;;
  start)
    sudo systemctl start "$SERVICE" && echo "Started $SERVICE"
    ;;
  *)
    echo "Usage: $0 [status|logs [N]|follow|restart|stop|start]"
    echo "  status       - show service status (default)"
    echo "  logs [N]     - show last N log lines (default 50)"
    echo "  follow       - tail logs live"
    echo "  restart      - restart the bot"
    echo "  stop/start   - stop or start the bot"
    ;;
esac
