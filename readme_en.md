# Atlantico Server — Federated Learning Server

This repository contains a Federation Learning server used to receive, aggregate
and redistribute neural network weights from devices (ESP32/Raspberry Pi clients).

Quick setup (Linux / Debian/Ubuntu):

1. Create and activate a virtual environment (recommended):

   python3 -m venv .venv
   source .venv/bin/activate

2. Install dependencies:

   pip install -r requirements.txt

3. Start a local Mosquitto broker using the repository-supplied helper (recommended for local development):

   # start broker in background (daemon-like)
   ./scripts/mosquitto_control.sh start_background

   # or run in the foreground (attached to your terminal)
   ./scripts/mosquitto_control.sh start

   # other helper actions: stop, restart, restart_background, status
   ./scripts/mosquitto_control.sh status

   (you may also use system mosquitto directly if preferred)

4. Run the server CLI using the repo helper (ensures repo root is CWD and prefers `.venv`):

   # show help
   ./scripts/start_server.sh --help

   # run a command, for example: list alive devices
   ./scripts/start_server.sh alive

   The helper will use `.venv/bin/python` if a `.venv` exists; activate the venv manually if you prefer.

Notes
- The project expects MQTT messages where metrics are JSON and model payloads are binary.
- Broker and logs are configured to use the `run/` directory so everything stays inside the repo.
- See `readme.md` (Portuguese) for more details about commands and internal layout.
