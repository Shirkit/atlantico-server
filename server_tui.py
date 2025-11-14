#!/usr/bin/env python3
"""
Atlantico Server - Terminal UI Mode

Entry point for running the atlantico server with a terminal-based GUI.
"""

import sys
from atlantico_server.server import MQTTFederatedServer
from atlantico_server.tui import ServerApp


def main():
    """Main entry point for TUI mode"""
    
    print("Initializing Atlantico Server...")
    
    # Initialize the MQTT federated server with logging to file only (no stdout in TUI mode)
    server = None
    try:
        server = MQTTFederatedServer(debug=False, enable_stdout=False)
        
        # Start MQTT loop in background
        server.client.loop_start()
        print("Connected to MQTT broker")
    except Exception as e:
        print(f"Warning: Could not connect to MQTT broker: {e}")
        print("Starting TUI in offline mode...")
        server = None
    
    print("Starting Terminal UI...")
    
    try:
        # Create and run the TUI app
        app = ServerApp(server=server)
        app.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean up
        if server:
            server.disconnect()
        print("Server stopped.")


if __name__ == "__main__":
    main()
