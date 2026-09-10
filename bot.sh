#!/usr/bin/env bash
# Start, stop, and inspect the SAT consensus bot.
set -euo pipefail

cd "$(dirname "$0")"
PIDFILE=".bot.pid"
LOGFILE="bot.log"
PY=".venv/bin/python"

running() {
  [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

case "${1:-}" in
  start)
    if running; then
      echo "already running (pid $(cat "$PIDFILE"))"
      exit 0
    fi
    pkill -9 -f "[-]m bot" 2>/dev/null || true
    sleep 1
    PYTHONPATH=src nohup "$PY" -u -m bot >> "$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 6
    if running; then
      echo "started (pid $(cat "$PIDFILE"))  ->  @mb1600SATBot"
      tail -n 2 "$LOGFILE"
    else
      echo "FAILED to start. Last log lines:"
      tail -n 15 "$LOGFILE"
      rm -f "$PIDFILE"
      exit 1
    fi
    ;;
  stop)
    if running; then
      kill "$(cat "$PIDFILE")" 2>/dev/null || true
      sleep 2
      kill -9 "$(cat "$PIDFILE")" 2>/dev/null || true
    fi
    pkill -9 -f "[-]m bot" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "stopped"
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  status)
    if running; then
      echo "RUNNING (pid $(cat "$PIDFILE"))"
    else
      echo "STOPPED"
    fi
    ;;
  logs)
    tail -n "${2:-40}" -f "$LOGFILE"
    ;;
  *)
    echo "usage: ./bot.sh {start|stop|restart|status|logs [n]}"
    exit 1
    ;;
esac
