# Atlantico Server — Federated Learning Server

This repository contains a Federation Learning server used to receive, aggregate
and redistribute neural network weights from devices (ESP32/Raspberry Pi clients).

Quick setup (Linux / Debian/Ubuntu):

1. Create and activate a virtual environment (recommended):

   python3 -m venv .venv
   source .venv/bin/activate

2. Install dependencies:

   pip install -r requirements.txt

3. Start a local Mosquitto broker using the repository config (recommended for local development):

   mosquitto -c run/mosquitto.conf

   (or install system mosquitto and run as a service)

4. Run the server CLI:

   python server.py --help

Notes
- The project expects MQTT messages where metrics are JSON and model payloads are binary.
- Broker and logs are configured to use the `run/` directory so everything stays inside the repo.
- See `readme.md` (Portuguese) for more details about commands and internal layout.
