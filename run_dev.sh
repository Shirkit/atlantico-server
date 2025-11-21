#!/bin/bash
# Dev mode launcher for Atlantico Server TUI with CSS hot reload

cd "$(dirname "$0")"

# Start textual console in background
echo "Starting Textual console..."
.venv/bin/textual console &
CONSOLE_PID=$!

# Give console time to start
sleep 2

# Run the TUI with hot reload enabled
echo "Starting TUI with CSS hot reload..."
.venv/bin/python -m textual run --dev server_tui.py

# Clean up console when done
kill $CONSOLE_PID 2>/dev/null
