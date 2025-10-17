#!/usr/bin/env bash
# Control script for running a repo-local mosquitto using run/mosquitto.conf

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR%/scripts}"
cd "$REPO_ROOT"

MOSQ_CONF="$REPO_ROOT/run/mosquitto.conf"
PID_FILE="$REPO_ROOT/run/mosquitto.pid"
LOG_FILE="$REPO_ROOT/run/logs/mosquitto.log"

start_background() {
  mkdir -p "$(dirname "$PID_FILE")" "$(dirname "$LOG_FILE")"
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "mosquitto is already running (pid $(cat "$PID_FILE"))"
    return 0
  fi
  echo "Starting mosquitto in background with config: $MOSQ_CONF"
  nohup mosquitto -c "$MOSQ_CONF" >>"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  sleep 0.2
  echo "Started mosquitto (pid $(cat "$PID_FILE"))"
}

# Start mosquitto in foreground attached to the current terminal
start() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "mosquitto appears to be running (pid $(cat "$PID_FILE")); stop it first or use start_background."
    return 1
  fi
  echo "Starting mosquitto in foreground with config: $MOSQ_CONF"
  # Run mosquitto attached to this terminal; logs will follow mosquitto.conf settings
  exec mosquitto -c "$MOSQ_CONF"
}

stop() {
  if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE")
    echo "Stopping mosquitto (pid $pid)"
    kill "$pid" || true
    rm -f "$PID_FILE"
  else
    echo "No PID file found; mosquitto may not be running"
  fi
}

status() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "mosquitto running (pid $(cat "$PID_FILE"))"
    tail -n 10 "$LOG_FILE" || true
    return 0
  else
    echo "mosquitto not running"
    return 1
  fi
}

case ${1:-} in
  start) start ;; 
  start_background) start_background ;;
  stop) stop ;; 
  restart) stop; start ;; 
  restart_background) stop; start_background ;;
  status) status ;; 
  *) echo "Usage: $0 {start|start_background|stop|restart|restart_background|status}"; exit 2 ;;
esac
