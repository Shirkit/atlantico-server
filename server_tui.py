#!/usr/bin/env python3
"""
Atlantico Server - Terminal UI Mode

Entry point for running the atlantico server with a terminal-based GUI.
"""

import sys
import logging
from atlantico_server.server import MQTTFederatedServer
from atlantico_server.tui import ServerApp
from atlantico_server.logging import setup_logging, get_logger

logger = get_logger('atlantico_server')


def main():
    """Main entry point for TUI mode"""
    
    # Setup logging for TUI mode (file only, no stdout to avoid interfering with TUI)
    setup_logging(debug=False, enable_stdout=False)
    
    logger.info("Initializing Atlantico Server")
    
    # Initialize the MQTT federated server with logging to file only (no stdout in TUI mode)
    server = None
    try:
        server = MQTTFederatedServer(debug=False, enable_stdout=False)
        
        # Start MQTT loop in background
        server.client.loop_start()
        logger.info("Connected to MQTT broker")
    except Exception as e:
        logger.warning(f"Could not connect to MQTT broker: {e}")
        logger.info("Starting TUI in offline mode")
        server = None
    
    logger.info("Starting Terminal UI")
    
    try:
        # Create and run the TUI app
        app = ServerApp(server=server)
        app.run()
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        # Clean up
        if server:
            server.disconnect()
        logger.info("Server stopped")


if __name__ == "__main__":
    main()
