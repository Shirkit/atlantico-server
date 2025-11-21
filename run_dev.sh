#!/bin/bash
# Dev mode launcher for Atlantico Server TUI with CSS hot reload

cd "$(dirname "$0")"

# Activate virtual environment
source .venv/bin/activate

# Start textual console in background
echo "Starting Textual console..."
textual console > /dev/null 2>&1 &
CONSOLE_PID=$!

# Give console time to start
# sleep 1

# Run the TUI with hot reload enabled
# echo "Starting TUI with CSS hot reload..."
textual run --dev server_tui.py

# Clean up console when done
kill $CONSOLE_PID 2>/dev/null
