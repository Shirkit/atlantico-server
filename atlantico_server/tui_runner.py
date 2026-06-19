#!/usr/bin/env python3
"""
Atlantico Server - Terminal UI Mode

Entry point for running the atlantico server with a terminal-based GUI.
"""

import sys
import os

# Ensure the parent directory is in the path so we can import atlantico_server
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from atlantico_server.server import MQTTFederatedServer
from atlantico_server.tui import ServerApp
from atlantico_server.log_setup import setup_logging, get_logger

logger = get_logger('atlantico_server')

def main():
    """Main entry point for TUI mode"""
    
    # Setup logging for TUI mode (file only, no stdout to avoid interfering with TUI)
    setup_logging(debug=True, enable_stdout=False)
    
    logger.info("--- Atlantico Server TUI Mode ---")
    logger.info("Initializing Atlantico Server")
    
    # Initialize the MQTT federated server with logging to file only (no stdout in TUI mode)
    server = None
    try:
        server = MQTTFederatedServer(debug=True, enable_stdout=False)
        # from atlantico_server.parser import plot_batch_comparison
        # plot_batch_comparison("/home/shirkit/Projects/atlantico-server/weights/batch_2025-12-29_12-34-23")
        # server.parse_all_training_data("/home/shirkit/Projects/atlantico-server/weights/batch_2025-12-29_12-34-23")
        
        # Start MQTT loop in background
        # server.client.loop_start()
        logger.info("Connected to MQTT broker")
    except Exception as e:
        logger.warning(f"Could not connect to MQTT broker: {e}")
        logger.info("Starting TUI in offline mode")
        server = None
    
    logger.info("Starting Terminal UI")
    
    try:
        # Create and run the TUI app
        app = ServerApp(server=server)
        app.run(headless=False)
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        # Clean up
        if server:
            server.disconnect()

# def create_app():
#     """Factory function for textual run command"""
#     setup_logging(debug=True, enable_stdout=False)
    
#     server = None
#     try:
#         server = MQTTFederatedServer(debug=False, enable_stdout=False)
#         server.client.loop_start()
#     except Exception as e:
#         logger.warning(f"Could not connect to MQTT broker: {e}")
    
#     return ServerApp(server=server)


# # App instance for textual run command
# app = create_app()

if __name__ == "__main__":
    main()
