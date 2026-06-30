"""Main server implementation (renamed from `novoServidor.py`).

This module contains the full MQTT federated server implementation. The
original `novoServidor.py` top-level script has been removed to avoid
duplication; use `python server.py` from the repo root or run
`python -m atlantico_server.server` to execute the CLI.
"""

import json
import paho.mqtt.client as mqtt
from datetime import datetime
from time import sleep
import time
import os
import uuid
import traceback
import math
import struct
import numpy as np
import argparse
import sys
from .parser import do_parse, plot_batch_comparison
from .reader import read_nn_binary_with_activation
from .log_setup import setup_logging

# Global configuration constants
BROKER_IP = os.getenv("MQTT_BROKER_HOST", "127.0.0.1")
BROKER_PORT = 1883
BROKER_KEEPALIVE = 60

# MQTT Topics (Defaults)
DEFAULT_TOPIC_PREFIX = "esp32"

# Directory paths
PARSE_FOLDER = "parse/"
PARSE_ALL_FOLDER = "parse_all/"
WEIGHTS_FOLDER = "weights/"
METRICS_FOLDER = "metrics/"
BATCH_CONFIG_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "batch-config"))

# Federated learning configuration
DEFAULT_LAYERS = [32, 200, 100, 50, 25, 18]
DEFAULT_ACTIVATION_FUNCTIONS = [1, 1, 1, 1, 6]
#DEFAULT_LAYERS = [3, 2000, 1100, 600, 330, 200, 120, 60, 30, 15, 6]
#DEFAULT_ACTIVATION_FUNCTIONS = [1, 1, 1, 1, 1, 1, 1, 1, 1, 6]
# DEFAULT_LAYERS = [3, 100, 80, 60, 40, 20, 10, 6]
# DEFAULT_ACTIVATION_FUNCTIONS = [1, 1, 1, 1, 1, 1, 6]
DEFAULT_EPOCHS = 1
DEFAULT_LEARNING_RATE_WEIGHTS = 0.3333 / 4.0
DEFAULT_LEARNING_RATE_BIASES = 0.0666 / 4.0
DEFAULT_RANDOM_SEED = 10
DEFAULT_SEND_JSON_WEIGHTS = False

# Timing constants
CONNECTION_WAIT_TIME = 10
COMMAND_RETRY_INTERVAL = 2
COMMAND_RETRIES = 6
STATUS_UPDATE_INTERVAL = 30


class FederatedServerState:
    """Class to manage federated server state"""
    
    def __init__(self):
        self.is_federated = False
        self.federated_path = ""
        self.batch_base_path = ""
        self.current_round = 0
        self.max_rounds = 0
        self.connected_clients = {}  # {device_id: {'last_seen': timestamp}}
        self.federated_clients = {}  # {device_id: {'round': int, 'progress': str, 'last_update': timestamp}}
        self.debug = False
        self.is_paused = False
        self.paused_aggregated_path = None  # Store path to aggregated weights when paused
        self.stop_requested = False  # Flag to gracefully stop federated learning
        self.waiting_for_parent_start = False
        self.parent_start_allowed = False
        self.parent_command_status = "pending"
        self.last_active_clients = []
        
        # Batch progress tracking
        self.current_test_index = 0
        self.total_tests = 0
        self.current_test_name = ""
        self.active_config = None
    
    @property
    def waiting_for_clients(self):
        """Dynamically compute waiting clients from federated_clients progress"""
        return [cid for cid, info in self.federated_clients.items() 
                if info.get('progress') not in ('Done', 'Completed')]
    
    def reset(self):
        """Reset server state"""
        self.is_federated = False
        self.federated_path = ""
        self.current_round = 0
        self.max_rounds = 0
        self.connected_clients.clear()
        self.federated_clients.clear()
        self.is_paused = False
        self.paused_aggregated_path = None
        self.stop_requested = False
        self.current_test_index = 0
        self.total_tests = 0
        self.current_test_name = ""
        self.active_config = None


from .strategies import Strategies

class MQTTFederatedServer:
    """Main federated learning server class"""
    
    def __init__(self, debug=False, enable_stdout=True, topic_prefix=DEFAULT_TOPIC_PREFIX):
        # Use a short, human-friendly id suffix (8 hex chars) for broker logs
        short_id = uuid.uuid4().hex[:8]
        self.client_id = f"{topic_prefix}-Aggregator-{short_id}"
        self.client = mqtt.Client(client_id=self.client_id, clean_session=True)
        self.state = FederatedServerState()
        self.debug = debug
        
        # Setup logging (file always, stdout optional)
        self.logger = setup_logging(debug=debug, enable_stdout=enable_stdout)

        # Setup topics
        self.topic_prefix = topic_prefix
        self.hierarchical_config = {
            "enabled": False,
            "parent_prefix": "aggregator",
            "process_type": "latest_asynchronous",
            "merge_strategy": "next_round_50_percent",
            "sliding_window": None
        }
        self.max_wait_time = None
        self._update_topics()
        
        # Event system
        self.events = {}
        self.strategies = Strategies(self)
        self._setup_strategies()
        
        # self._setup_mqtt_client()

    def register_event_handler(self, event_name, callback, priority=5):
        """Register a callback for an event with priority (higher runs later)"""
        if event_name not in self.events:
            self.events[event_name] = []
        # Store as tuple (priority, callback)
        self.events[event_name].append((priority, callback))
        # Sort by priority
        self.events[event_name].sort(key=lambda x: x[0])

    def fire_event(self, event_name, data=None):
        """Fire an event and call all registered callbacks"""
        if event_name in self.events:
            result = True
            for priority, callback in self.events[event_name]:
                try:
                    this_result = callback(data)
                    if this_result is not None:
                        result = result and this_result
                except Exception as e:
                    self.logger.error(f"Error in event handler for {event_name}: {e}")
            return result

    def _setup_strategies(self):
        """Setup strategies based on configuration"""
        # Clear existing handlers for strategy events
        self.events = {}
        self.strategies.setup()

    def _update_topics(self):
        """Update MQTT topics based on prefix"""
        # Topics for my devices (I am the server)
        self.TOPIC_RECEIVE_FROM_DEVICES = f"{self.topic_prefix}/fl/model/push"
        self.TOPIC_RECEIVE_FROM_DEVICES_RAW = f"{self.topic_prefix}/fl/model/rawpush/+"
        self.TOPIC_SEND_TO_DEVICES = f"{self.topic_prefix}/fl/model/pull"
        self.TOPIC_SEND_TO_DEVICES_RAW = f"{self.topic_prefix}/fl/model/rawpull"
        self.TOPIC_RECEIVE_COMMANDS_FROM_DEVICES = f"{self.topic_prefix}/fl/commands/push"
        self.TOPIC_SEND_COMMANDS_TO_DEVICES = f"{self.topic_prefix}/fl/commands/pull"
        self.TOPIC_RESUME_TO_DEVICES = f"{self.topic_prefix}/fl/model/resume"
        self.TOPIC_RESUME_TO_DEVICES_RAW = f"{self.topic_prefix}/fl/model/rawresume"
        
        # Topics for my parent (I am the client)
        if self.hierarchical_config["enabled"]:
            pp = self.hierarchical_config["parent_prefix"]
            cid = self.client_id
            self.TOPIC_RECEIVE_FROM_PARENT = f"{pp}/fl/model/pull"
            self.TOPIC_RECEIVE_FROM_PARENT_RAW = f"{pp}/fl/model/rawpull"
            self.TOPIC_RECEIVE_COMMANDS_FROM_PARENT = f"{pp}/fl/commands/pull"
            
            self.TOPIC_SEND_TO_PARENT = f"{pp}/fl/model/push"
            self.TOPIC_SEND_TO_PARENT_RAW = f"{pp}/fl/model/rawpush/{cid}"
            self.TOPIC_SEND_COMMANDS_TO_PARENT = f"{pp}/fl/commands/push"

    def update_hierarchical_config(self, config):
        """Update hierarchical configuration"""
        # If the mode is changing from enabled to disabled, unsubscribe from parent topics
        was_enabled = self.hierarchical_config.get("enabled", False)
        self.hierarchical_config.update(config)
        is_enabled = self.hierarchical_config.get("enabled", False)
        
        if was_enabled and not is_enabled:
            if hasattr(self, 'TOPIC_RECEIVE_FROM_PARENT'):
                try:
                    self.client.unsubscribe([
                        self.TOPIC_RECEIVE_FROM_PARENT,
                        self.TOPIC_RECEIVE_FROM_PARENT_RAW,
                        self.TOPIC_RECEIVE_COMMANDS_FROM_PARENT
                    ])
                    self.logger.info("Unsubscribed from parent topics because hierarchical mode was disabled.")
                except Exception as e:
                    self.logger.warning(f"Failed to unsubscribe from parent topics: {e}")
                    
        self._setup_strategies()
        self._update_topics()

    def update_topic_prefix(self, prefix):
        """Update topic prefix and refresh topics"""
        if self.client.is_connected():
            old_topics = [
                self.TOPIC_RECEIVE_FROM_DEVICES,
                self.TOPIC_RECEIVE_FROM_DEVICES_RAW,
                self.TOPIC_RECEIVE_COMMANDS_FROM_DEVICES
            ]
            self.client.unsubscribe(old_topics)

        self.topic_prefix = prefix
        self._update_topics()
        short_id = uuid.uuid4().hex[:8]
        self.client_id = f"{self.topic_prefix}-Aggregator-{short_id}"
        # Only change client_id if we were to reconnect, but for now just updating prefix is enough for topics
        
        if self.client.is_connected():
            new_topics = [
                (self.TOPIC_RECEIVE_FROM_DEVICES, 0),
                (self.TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
                (self.TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
            ]
            self.client.subscribe(new_topics)
        
    def _setup_mqtt_client(self):
        """Configure MQTT client"""
        self.client.connect(BROKER_IP, BROKER_PORT, BROKER_KEEPALIVE)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc != 0:
            self.logger.error(f"MQTT connection failed with code: {rc}")
        else:
            if self.hierarchical_config["enabled"]:
                self.logger.info("Subscribing to parent topics")
                client.subscribe([
                    (self.TOPIC_RECEIVE_FROM_PARENT, 0),
                    (self.TOPIC_RECEIVE_FROM_PARENT_RAW, 0),
                    (self.TOPIC_RECEIVE_COMMANDS_FROM_PARENT, 0),
                ])
            
    def _on_message(self, client, userdata, message):
        """MQTT message callback"""
        try:
            topic = message.topic
            topic_parts = topic.split('/')
            self.logger.debug(f"Message received on topic: {topic}")
            
            # Handle Parent Messages (Hierarchical Mode)
            if self.hierarchical_config["enabled"]:
                if topic == self.TOPIC_RECEIVE_COMMANDS_FROM_PARENT:
                    self._handle_parent_command(message.payload.decode("utf-8"))
                    return
                elif topic == self.TOPIC_RECEIVE_FROM_PARENT_RAW:
                    self._handle_parent_raw_model(message.payload)
                    return

            # Handle Device Messages
            if topic_parts[2] == "model" and topic_parts[3] == "rawpush":
                if self.debug:
                    self.logger.debug('Receiving neural network file')
                self._handle_raw_push_message(topic_parts, message.payload)
            elif topic_parts[2] == "model" and topic_parts[3] == "push":
                if self.debug:
                    self.logger.debug('Receiving model message')
                self._handle_model_message(message.payload.decode("utf-8"))
            elif topic_parts[2] == "commands":
                self._handle_command_message(message.payload.decode("utf-8"))
                
        except UnicodeDecodeError as e:
            self.logger.error(f"Decoding message: {e}")
            self.logger.error(f"Payload: {message.payload}")
        except json.JSONDecodeError as e:
            self.logger.error(f"Decoding JSON: {e}")
            self.logger.error(f"Payload: {message.payload}")
        except Exception as e:
            self.logger.error(f"Unexpected error processing message: {e}")
            self.logger.error(traceback.format_exc())
    
    def _handle_raw_push_message(self, topic_parts, payload):
        """Handle raw neural network file uploads"""
        client_name = topic_parts[4]
        
        if self.state.is_federated:
            filepath = os.path.join(
                self.state.federated_path, 
                str(self.state.current_round), 
                f"{client_name}.nn"
            )
        else:
            filepath = os.path.join(WEIGHTS_FOLDER, f"{client_name}.nn")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'wb') as f:
            f.write(payload)
        
        # Update federated client progress tracking
        if client_name in self.state.federated_clients:
            self.state.federated_clients[client_name]['received_nn'] = True
            if self.state.federated_clients[client_name].get('received_json', False):
                self.state.federated_clients[client_name]['progress'] = 'Done'
            self.state.federated_clients[client_name]['last_update'] = time.time()
            
    def _handle_model_message(self, payload):
        """Handle model JSON data"""
        self._save_model_to_json(payload)
        
    def _handle_command_message(self, payload):
        """Handle command messages from clients"""
        try:
            command_data = json.loads(payload)
            command = command_data.get("command")
            client_id = command_data.get("client")
            
            if not command:
                self.logger.warning("Command not specified in message")
                return
                
            if self.state.is_federated:
                self._handle_federated_command(command, client_id, command_data)
            elif command == "resume":
                self._handle_resume_inactive(client_id)
            elif command == "alive":
                self._handle_alive_command(client_id)
            else:
                self.logger.warning(f"Unrecognized command: {payload}")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Processing command: {e}")

    def _handle_parent_command(self, payload):
        """Handle commands from parent aggregator"""
        try:
            command_data = json.loads(payload)
            
            # If "client" target is specified, ignore if it is not us
            target_client = command_data.get("client")
            if target_client is not None and target_client != self.client_id:
                # Targeted command not for us, ignore it
                return
                
            command = command_data.get("command")
            
            if command == "federate_alive":
                # Respond with alive
                self._send_to_parent({"command": "alive", "client": self.client_id}, is_command=True)
            elif command == "federate_start":
                self.logger.info("Received start command from parent aggregator")
                config = command_data.get("config", {})
                if "sliding_window" in config:
                    self.hierarchical_config["sliding_window"] = config["sliding_window"]
                    self.logger.info(f"Updated sliding_window to {config['sliding_window']} from parent config")
                
                # Release wait gate if waiting
                if hasattr(self, 'state'):
                    self.state.parent_command_status = "started"
                    self.state.waiting_for_parent_start = False
            elif command == "request_model":
                self.push_model_to_parent()
            elif command == "federate_join":
                self.logger.info("Received join request from parent aggregator")
                self.join_parent()
            elif command == "federate_unsubscribe":
                self.logger.info("Received unsubscribe command from parent aggregator")
                if hasattr(self, 'state'):
                    self.state.parent_command_status = "canceled"
                    self.state.waiting_for_parent_start = False
            elif command == "federate_stop" or (command == "federate_end" and target_client is not None):
                self.logger.info(f"Received {command} command (targeted/stop) from parent aggregator. Disabling parent connection.")
                if hasattr(self, 'state'):
                    self.state.parent_command_status = "canceled"
                    self.state.waiting_for_parent_start = False
                new_config = self.hierarchical_config.copy()
                new_config["enabled"] = False
                self.update_hierarchical_config(new_config)
            elif command == "federate_end":
                self.logger.info("Received federate_end command from parent aggregator. Finalizing current test.")
                if hasattr(self, 'state'):
                    self.state.parent_command_status = "canceled"
                    self.state.waiting_for_parent_start = False
                
        except Exception as e:
            self.logger.error(f"Error handling parent command: {e}")

    def _handle_parent_raw_model(self, payload):
        """Handle global model received from parent"""
        self.logger.info("Received global model from parent aggregator")
        # Save as 'parent_model.nn' in weights folder or current round folder
        try:
            path = os.path.join(WEIGHTS_FOLDER, "parent_model.nn")
            with open(path, "wb") as f:
                f.write(payload)
            
            # Fire event
            self.fire_event("on_parent_model_received", {"model_path": path})
            
        except Exception as e:
            self.logger.error(f"Error saving parent model: {e}")

    def _send_to_parent(self, data, is_command=False, topic=None):
        """Send data to parent aggregator"""
        if not self.hierarchical_config["enabled"]:
            return
            
        try:
            if is_command or topic is self.TOPIC_SEND_COMMANDS_TO_PARENT:
                topic = self.TOPIC_SEND_COMMANDS_TO_PARENT
                payload = json.dumps(data)
            elif topic is not None and topic is self.TOPIC_SEND_TO_PARENT:
                payload = json.dumps(data)
            else:
                # Assume data is binary model content
                topic = self.TOPIC_SEND_TO_PARENT_RAW
                payload = data
                
            self.client.publish(topic, payload)
        except Exception as e:
            self.logger.error(f"Error sending to parent: {e}")

    def join_parent(self):
        """Send join command to parent aggregator"""
        if self.hierarchical_config["enabled"]:
            self.logger.info(f"Joining parent aggregator as {self.client_id}")
            join_payload = {
                "command": "join",
                "client": self.client_id,
                "config": {
                    "process_type": self.hierarchical_config.get("process_type"),
                    "merge_strategy": self.hierarchical_config.get("merge_strategy"),
                    "aggregation_algorithm": self.hierarchical_config.get("aggregation_algorithm"),
                }
            }
            self._send_to_parent(join_payload, is_command=True)

    def leave_parent(self):
        """Send leave command to parent aggregator"""
        if self.hierarchical_config["enabled"]:
            self.logger.info(f"Leaving parent aggregator as {self.client_id}")
            self._send_to_parent({"command": "leave", "client": self.client_id}, is_command=True)

    def push_model_to_parent(self, model_path=None):
        """Push aggregated model to parent aggregator"""
        if not self.hierarchical_config["enabled"]:
            return

        if model_path is None:
            # Default to aggregated weights
             model_path = os.path.join(WEIGHTS_FOLDER, "aggregated_weights.nn")
             if self.state.is_federated:
                 model_path = os.path.join(self.state.federated_path, str(self.state.current_round), "aggregated_weights.nn")

        if os.path.exists(model_path):
            self.logger.info(f"Pushing model to parent: {model_path}")
            with open(model_path, "rb") as f:
                content = f.read()
                self._send_to_parent(content, is_command=False)

                combined_metrics = {
                    "round": self.state.current_round,
                    "clients": {},
                    "client": self.client_id
                }
                for client_id in self.state.federated_clients.keys():
                    client_metrics_path = os.path.join(
                        self.state.federated_path,
                        str(self.state.current_round),
                        f"{client_id}_metrics.json"
                    )
                    if os.path.exists(client_metrics_path):
                        with open(client_metrics_path, "r") as f:
                            client_metrics = json.load(f)
                            combined_metrics["clients"][client_id] = client_metrics
                self._send_to_parent(combined_metrics, topic=self.TOPIC_SEND_TO_PARENT)
                self.fire_event("on_model_pushed_to_parent", {"model_path": model_path, "round": self.state.current_round})
                
            # Also send JSON metadata if needed
            # self._send_to_parent({...}, is_command=False, topic=self.TOPIC_SEND_TO_PARENT)
        else:
            self.logger.warning("No model to push to parent")
    
    def _handle_federated_command(self, command, client_id, command_data):
        """Handle federated learning specific commands"""
        if command == "join":
            self._handle_join_command(client_id, command_data)
        elif command == "leave":
            self._handle_leave_command(client_id)
        elif command == "resume":
            self._handle_resume_command(client_id)
        elif command == "alive":
            # Always track alive status for all devices, regardless of federation participation
            self._handle_alive_command(client_id, auto_discover=True)
    
    def _handle_join_command(self, client_id, command_data=None):
        """Handle client join requests for federation"""
        # Ensure device is tracked in connected_clients
        if client_id not in self.state.connected_clients:
            self.state.connected_clients[client_id] = {'last_seen': time.time()}
        else:
            self.state.connected_clients[client_id]['last_seen'] = time.time()
        
        # Extract config from join command
        client_config = {}
        if command_data and "config" in command_data:
            client_config = command_data["config"]
        
        # Add to federated_clients if not already there (device wants to participate)
        if client_id not in self.state.federated_clients:
            self.state.federated_clients[client_id] = {
                'round': self.state.current_round if self.state.current_round > 0 else 1,
                'progress': 'Waiting',
                'last_update': time.time(),
                'config': client_config
            }
            self.logger.info(f"Client {client_id} joined federation with options {client_config}. "
                      f"Federated clients: {len(self.state.federated_clients)}")
        else:
            self.state.federated_clients[client_id]['config'] = client_config
    
    def _handle_leave_command(self, client_id):
        """Handle client leave notifications from federation"""
        # Remove from federated_clients but keep in connected_clients
        if client_id in self.state.federated_clients:
            del self.state.federated_clients[client_id]
            self.logger.info(f"Client {client_id} left federation. "
                      f"Federated clients: {len(self.state.federated_clients)}")
            
            # Orchestrate standalone fallback on the parent
            if len(self.state.federated_clients) == 1:
                last_client_id = list(self.state.federated_clients.keys())[0]
                self.logger.info(f"Only one client remaining ({last_client_id}). Sending targeted federate_end command.")
                end_command = {
                    "command": "federate_end",
                    "client": last_client_id
                }
                self._send_command(json.dumps(end_command, separators=(',', ':')))


    
    def _handle_resume_command(self, client_id):
        """Handle client resume notifications"""
        # Only allow resuming if the client is actively registered as part of the current federated learning session
        if client_id not in self.state.federated_clients:
            self.logger.warning(f"Client {client_id} requested resume, but was not part of the active federated session. Rejecting.")
            self._handle_resume_inactive(client_id)
            return

        # Ensure client is marked as connected/seen
        if client_id not in self.state.connected_clients:
            self.state.connected_clients[client_id] = {'last_seen': time.time()}
        else:
            self.state.connected_clients[client_id]['last_seen'] = time.time()
            
        self.logger.info(f"Client {client_id} is ready to continue")
        try:
            resume_command = {
                "command": "federate_resume",
                "client": client_id,
                "round": self.state.current_round
            }
            if self.state.active_config is not None:
                resume_command["config"] = self.state.active_config

            self._send_command(json.dumps(resume_command, separators=(',', ':')))
            
            # Try to send binary .nn file first, fallback to JSON
            aggregated_binary_path = os.path.join(
                self.state.federated_path,
                str(self.state.current_round - 1),
                "aggregated_weights.nn"
            )
            
            if os.path.exists(aggregated_binary_path):
                self.logger.debug(f"Sending binary resume file to {client_id}")
                self._send_binary_file(aggregated_binary_path, f"{self.TOPIC_RESUME_TO_DEVICES_RAW}/{client_id}")
            else:
                # Fallback to JSON if binary file doesn't exist
                aggregated_json_path = os.path.join(
                    self.state.federated_path,
                    str(self.state.current_round - 1),
                    "aggregated_weights.json"
                )
                self.logger.debug(f"Binary file not found, sending JSON to {client_id}")
                self._send_file(aggregated_json_path, self.TOPIC_RESUME_TO_DEVICES)
            
        except Exception as e:
            self.logger.error(f"Sending weights file: {e}")

    def _handle_resume_inactive(self, client_id):
        """Send a negative resume reply to indicate that no training session is running"""
        self.logger.info(f"Client {client_id} requested resume, but no active federation is running. Sending stop command.")
        response = {
            "command": "federate_stop",
            "client": client_id,
            "reason": "no_active_session"
        }
        self._send_command(json.dumps(response, separators=(',', ':')))
    
    def _handle_alive_command(self, client_id, auto_discover=True):
        """Handle alive messages"""
        # Auto-discovery: add to connected_clients if not already there
        if auto_discover and client_id not in self.state.connected_clients:
            self.state.connected_clients[client_id] = {'last_seen': time.time()}
        else:
            # Update last_seen timestamp
            if client_id in self.state.connected_clients:
                self.state.connected_clients[client_id]['last_seen'] = time.time()
    
    def _save_model_to_json(self, data):
        """Save received model data to JSON file"""
        try:
            loaded_data = json.loads(data)
            output_data = {
                "received_time": datetime.now().isoformat(),
                "data": loaded_data,
            }
            
            client_name = output_data["data"]["client"]
            
            if self.state.is_federated:
                filepath = os.path.join(
                    self.state.federated_path,
                    str(self.state.current_round),
                    f"{client_name}.json"
                )
            else:
                filepath = os.path.join(WEIGHTS_FOLDER, f"{client_name}.json")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # Update federated client progress tracking
            if client_name in self.state.federated_clients:
                self.state.federated_clients[client_name]['received_json'] = True
                if self.state.federated_clients[client_name].get('received_nn', False):
                    self.state.federated_clients[client_name]['progress'] = 'Done'
                self.state.federated_clients[client_name]['last_update'] = time.time()
            
            try:
                with open(filepath, 'x') as json_file:
                    json.dump(output_data, json_file, indent=4, separators=(',', ':'))
            except FileExistsError:
                self.logger.debug(f"JSON file already exists: {filepath}, ignoring")
                # File already exists, probably received twice - ignore
                pass
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Decoding JSON: {e}")
            self.logger.error(f"Received data: {data}")
    
    def _send_command(self, command_data, topic=None):
        """Send command via MQTT"""
        if topic is None:
            topic = self.TOPIC_SEND_COMMANDS_TO_DEVICES
        try:
            if self.debug:
                self.logger.debug("Sending command via MQTT")
            self.client.publish(topic, command_data)
        except Exception as e:
            self.logger.error(f"Sending command via MQTT: {e}")
    
    def _send_file(self, filepath, topic=None):
        """Send file content via MQTT"""
        if topic is None:
            topic = self.TOPIC_SEND_TO_DEVICES
        try:
            if os.path.exists(filepath):
                with open(filepath, "r") as file:
                    content = file.read().strip()
                    self.client.publish(topic, content)
            else:
                self.logger.error(f"File {filepath} not found")
        except Exception as e:
            self.logger.error(f"Sending file via MQTT: {e}")
    
    def _read_binary_nn_file(self, filepath):
        """Read binary .nn file with ESP32 format"""
        try:
            # Use the reader with activation function support
            network = read_nn_binary_with_activation(filepath, logger=self.logger)
            
            if network is not None:
                # Convert to the format expected by the aggregation code
                network_data = {
                    'numberOflayers': network['num_layers'],
                    'layers': []
                }
                
                for layer in network['layers']:
                    layer_info = {
                        'inputs': layer['inputs'],
                        'outputs': layer['outputs'],
                        'activation_function': layer.get('activation', 'relu'),
                        'biases': layer['biases'],
                        'weights': layer['weights']
                    }
                    network_data['layers'].append(layer_info)
                
                return network_data
            else:
                self.logger.error(f"Failed to load neural network from {filepath}")
                return None
            
        except Exception as e:
            self.logger.error(f"Reading file {filepath}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _write_binary_nn_file(self, filepath, network_data):
        """Write neural network to binary .nn file using the ESP32 format with activation functions"""
        try:
            with open(filepath, 'wb') as file:
                # Write number of layers
                file.write(struct.pack('<I', network_data['numberOflayers']))
                
                for layer in network_data['layers']:
                    # Write activation function byte (required by ESP32 with ACTIVATION__PER_LAYER)
                    # Map activation function names to ESP32 enum values
                    activation_map = {
                        'sigmoid': 0,
                        'tanh': 1,
                        'relu': 2,
                        'leakyrelu': 3,
                        'elu': 4,
                        'selu': 5,
                        'softmax': 6
                    }
                    activation_name = layer.get('activation_function', 'relu').lower()
                    activation_byte = activation_map.get(activation_name, 2)  # Default to ReLU (2)
                    file.write(struct.pack('<B', activation_byte))
                    
                    # Write layer inputs and outputs
                    file.write(struct.pack('<I', layer['inputs']))
                    file.write(struct.pack('<I', layer['outputs']))
                    
                    # Write biases and weights for each output neuron (MULTIPLE_BIASES_PER_LAYER format)
                    for j in range(layer['outputs']):
                        # Write bias for this output neuron
                        file.write(struct.pack('<f', float(layer['biases'][j])))
                        
                        # Write weights for this output neuron (from all inputs)
                        for k in range(layer['inputs']):
                            file.write(struct.pack('<f', float(layer['weights'][j][k])))
            
            return True
            
        except Exception as e:
            self.logger.error(f"Writing binary file {filepath}: {e}")
            return False
    
    def _send_binary_file(self, filepath, topic=None):
        """Send binary file content via MQTT"""
        if topic is None:
            topic = self.TOPIC_SEND_TO_DEVICES_RAW
        try:
            if os.path.exists(filepath):
                with open(filepath, "rb") as file:
                    content = file.read()
                    self.logger.debug(f"Sending binary file ({len(content)/1024:.1f} KB)")
                    self.client.publish(topic, content)
            else:
                self.logger.error(f"Binary file {filepath} not found")
        except Exception as e:
            self.logger.error(f"Sending binary file via MQTT: {e}")

    def aggregate_weights(self, round_number=-1):
        """Aggregate neural network weights from multiple clients using binary .nn files with JSON fallback"""
        if self.state.is_federated:
            source_dir = os.path.join(self.state.federated_path, str(self.state.current_round))
            files = os.listdir(source_dir)
        else:
            source_dir = WEIGHTS_FOLDER
            files = os.listdir(source_dir)
        
        # PRIMARY METHOD: Try binary .nn files first
        nn_files = [f for f in files if f.endswith('.nn') and f != "aggregated_weights.nn"]
        
        # Filter to only include files from federated clients
        if self.state.federated_clients:
            federated_device_ids = set(self.state.federated_clients.keys())
            nn_files = [f for f in nn_files if any(device_id in f for device_id in federated_device_ids)]
        
        if nn_files:
            result = self.fire_event("on_round_aggregation_started", {"round": round_number, "files": nn_files, "method": "binary"})
            if result:
                nn_files = result
            path = self._aggregate_weights_binary(source_dir, nn_files, round_number)
            if path:
                self.fire_event("on_round_aggregation_completed", {"model_path": path, "round": round_number})
            return path
        else:
            # FALLBACK METHOD: Use JSON files if no .nn files found
            self.logger.warning("No .nn files found, trying JSON fallback method")
            json_files = [f for f in files if f.endswith('.json') and f != "aggregated_weights.json"]
            
            if json_files:
                self.logger.debug(f"Using JSON fallback method: {len(json_files)} JSON files found")
                result = self.fire_event("on_round_aggregation_started", {"round": round_number, "files": json_files, "method": "json"})
                if result:
                    json_files = result
                path = self._aggregate_weights_json(source_dir, json_files, round_number)
                if path:
                    self.fire_event("on_round_aggregation_completed", {"model_path": path, "round": round_number})
                return path
            else:
                self.logger.error("No .nn or .json files found for aggregation")
                return None

    def _aggregate_weights_binary(self, source_dir, nn_files, round_number):
        """Aggregate using binary .nn files (primary method)"""
        self.logger.info(f"Aggregating {len(nn_files)} binary models (round {round_number})")
        
        # Read binary neural network data
        networks = []
        for file in nn_files:
            filepath = os.path.join(source_dir, file)
            network_data = self._read_binary_nn_file(filepath)
            if network_data is not None:
                networks.append(network_data)
                 
        if not networks:
            self.logger.error("No valid data for binary aggregation")
            return None

        # Use the configured aggregation strategy
        aggregated_network = self.strategies.aggregate(networks)
        
        if aggregated_network is None:
            self.logger.error("Aggregation failed")
            return None
            
        if self.debug:
            for layer_idx, layer in enumerate(aggregated_network['layers']):
                self.logger.debug(f"Layer {layer_idx}: {layer['inputs']} → {layer['outputs']}")
        
        # Save aggregated network as binary file
        if self.state.is_federated:
            output_path = os.path.join(
                self.state.federated_path,
                str(self.state.current_round),
                "aggregated_weights.nn"
            )
        else:
            output_path = os.path.join(WEIGHTS_FOLDER, "aggregated_weights.nn")
        
        # Write binary aggregated weights
        success = self._write_binary_nn_file(output_path, aggregated_network)
        
        if success:
            self.logger.info(f"Aggregated {len(networks)} valid models")
            
            # Also save as JSON for compatibility/debugging with parser.py
            json_output_path = output_path.replace('.nn', '.json')
            
            # Convert aggregated network to flat format for JSON compatibility
            all_biases = []
            all_weights = []
            
            for layer in aggregated_network['layers']:
                # Flatten biases
                all_biases.extend(layer['biases'].tolist())
                
                # Flatten weights (row-major order)
                for neuron_weights in layer['weights']:
                    all_weights.extend(neuron_weights.tolist())
            
            aggregated_json = {
                "precision": "float",
                "biases": all_biases,
                "weights": all_weights
            }
            
            if round_number >= 0:
                aggregated_json["round"] = round_number
                
            with open(json_output_path, 'w') as f:
                json.dump(aggregated_json, f, indent=4, separators=(',', ':'))
            
            return output_path
        else:
            self.logger.error("Failed to save aggregated weights")
            return None

    def _aggregate_weights_json(self, source_dir, json_files, round_number):
        """Aggregate using JSON files (fallback method)"""
        # Read JSON data (old method)
        json_data = []
        for file in json_files:
            filepath = os.path.join(source_dir, file)
            with open(filepath, 'r') as f:
                data = json.load(f)
                json_data.append(data)
        
        # Prepare aggregated structure
        aggregated = {
            "precision": "float",  # TODO: make configurable
            "biases": [],
            "weights": []
        }
        
        if round_number >= 0:
            aggregated["round"] = round_number
        
        if not json_data:
            self.logger.error("No valid data for JSON aggregation")
            return None
        
        # Get dimensions from first valid entry
        first_data = json_data[0]["data"]
        bias_length = len(first_data["biases"])
        weights_length = len(first_data["weights"])
        
        # Identify entries to skip (invalid mean squared error)
        skip_indices = []
        for i, data in enumerate(json_data):
            mse = data["data"]["metrics"]["meanSqrdError"]
            if mse is None or math.isnan(mse):
                skip_indices.append(i)
        
        valid_count = len(json_data) - len(skip_indices)
        if valid_count == 0:
            self.logger.error("No valid data found for JSON aggregation")
            return None
        
        self.logger.info(f"Aggregating {valid_count} valid models (JSON fallback method)")
        
        # Aggregate biases
        for i in range(bias_length):
            bias_sum = 0
            for k, data in enumerate(json_data):
                if k not in skip_indices:
                    bias_sum += float(data["data"]["biases"][i])
            aggregated["biases"].append(bias_sum / valid_count)
        
        # Aggregate weights
        for i in range(weights_length):
            weight_sum = 0
            for k, data in enumerate(json_data):
                if k not in skip_indices:
                    weight_sum += float(data["data"]["weights"][i])
            aggregated["weights"].append(weight_sum / valid_count)
        
        # Save aggregated weights (JSON method only saves JSON)
        if self.state.is_federated:
            output_path = os.path.join(
                self.state.federated_path,
                str(self.state.current_round),
                "aggregated_weights.json"
            )
        else:
            output_path = os.path.join(WEIGHTS_FOLDER, "aggregated_weights.json")
        
        with open(output_path, 'w') as f:
            json.dump(aggregated, f, indent=4, separators=(',', ':'))
        
        self.logger.info(f"Aggregated weights saved to: {output_path}")
        self.logger.info(f"Aggregated {valid_count} valid models from {len(json_data)} total (JSON method)")
        
        # Fire aggregation completed event
        self.fire_event("on_round_aggregation_completed", {"model_path": output_path, "round": round_number})
        
        return output_path
    
    def start_federated_learning(self, max_rounds=None, expected_clients=None):
        """Start federated learning process"""
        self.logger.info("Starting Federated Learning")
        
        # Setup MQTT subscriptions
        topics = [
            (self.TOPIC_RECEIVE_FROM_DEVICES, 0),
            (self.TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (self.TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
        
        if self.hierarchical_config["enabled"]:
            topics.extend([
                (self.TOPIC_RECEIVE_COMMANDS_FROM_PARENT, 0),
                (self.TOPIC_RECEIVE_FROM_PARENT_RAW, 0),
                (self.TOPIC_RECEIVE_FROM_PARENT, 0)
            ])
            self.join_parent()
            
        self.client.subscribe(topics)
        self.client.loop_start()
        
        # Get configuration from user or parameters
        try:
            if max_rounds is not None:
                max_rounds = max_rounds
            else:
                max_rounds = int(input("\nEnter the number of rounds for the federated process: "))
            
            if expected_clients is not None:
                expected_clients = expected_clients
            else:
                expected_clients = int(input("Enter the expected number of clients: "))
        except ValueError:
            self.logger.error("Invalid input. Exiting")
            return
        
        # Create default test configuration
        test_config = {
            "name": "federated_learning",
            "epochs": DEFAULT_EPOCHS,
            "rounds": max_rounds,
            "layers": DEFAULT_LAYERS,
            "activationFunctions": DEFAULT_ACTIVATION_FUNCTIONS,
            "learningRateWeights": DEFAULT_LEARNING_RATE_WEIGHTS,
            "learningRateBiases": DEFAULT_LEARNING_RATE_BIASES,
            "seed": DEFAULT_RANDOM_SEED,
            "sendJsonWeights": DEFAULT_SEND_JSON_WEIGHTS
        }
        
        self.logger.info(f"Configuration: {max_rounds} rounds, {expected_clients} clients expected")
        
        # Run single federated learning session using shared code
        success = self._run_single_batch_test(test_config, 1, expected_clients, None)
        
        if success:
            # Use the shared finalization
            self._finalize_single_batch_test()
            self.logger.info("Federated learning completed successfully.")
        else:
            self.logger.error("Federated learning failed.")
        
        # Cleanup
        self._cleanup_federated_learning()
    
    def _save_federated_config(self, start_command, test_config=None, test_number=None):
        """Save federated learning configuration"""
        config = start_command["config"].copy()
        config["devices"] = sorted(self.state.connected_clients)
        
        # Add batch-specific info if available
        if test_config and test_number:
            config.update({
                "batch_test_number": test_number,
                "batch_test_name": test_config.get('name', f'batch_test_{test_number}'),
            })
        
        # Calculate neural network parameters
        layers = config["layers"]
        total_neurons = sum(layers[i] * layers[i+1] for i in range(len(layers) - 1))
        
        config.update({
            "neurons": total_neurons,
            "device_count": len(self.state.federated_clients),
            "bits": "32",
            "run": "X",
            "server": {
                "client_id": self.client_id,
                "broker_host": BROKER_IP,
                "broker_port": BROKER_PORT,
                "topic_prefix": self.topic_prefix,
                "hierarchical": {
                    "enabled": self.hierarchical_config.get("enabled", False),
                    "parent_prefix": self.hierarchical_config.get("parent_prefix"),
                    "client_id": self.hierarchical_config.get("client_id")
                }
            }
        })
        
        config_path = os.path.join(self.state.federated_path, "config.json")
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4, separators=(',', ':'))
    
    def _send_unsubscribe_command(self):
        """Send unsubscribe command to all clients"""
        unsubscribe_command = {"command": "federate_unsubscribe"}
        self._send_command(json.dumps(unsubscribe_command, separators=(',', ':')))
    
    def _cleanup_federated_learning(self):
        """Clean up federated learning state"""
        self.leave_parent()
        self.state.reset()
    
    def pause_federated_learning(self):
        """Pause federated learning - continue aggregation but don't send weights"""
        if not self.state.is_federated:
            self.logger.error("Federated learning is not active")
            return False
        
        if self.state.is_paused:
            self.logger.warning("Federated learning is already paused")
            return False
        
        self.state.is_paused = True
        self.logger.info("Federated learning paused")
        return True
    
    def resume_federated_learning(self):
        """Resume federated learning - send accumulated weights"""
        if not self.state.is_federated:
            self.logger.error("Federated learning is not active")
            return False
        
        if not self.state.is_paused:
            self.logger.warning("Federated learning is not paused")
            return False
        
        self.state.is_paused = False
        self.logger.info("Federated learning resumed")
        return True
    
    def stop_federated_learning(self):
        """Request graceful stop of federated learning"""
        if not self.state.is_federated:
            self.logger.error("Federated learning is not active")
            return False
        
        if self.state.stop_requested:
            self.logger.warning("Stop already requested")
            return False
        
        self.state.stop_requested = True
        self.logger.info("Requesting graceful stop of federated learning")
        return True
    
    def start_listening_mode(self):
        """Start listening mode - just receive and save messages"""
        self.logger.info("Starting listening mode")
        self.client.loop_stop()
        
        topics = [
            (self.TOPIC_RECEIVE_FROM_DEVICES, 0),
            (self.TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (self.TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
        self.client.subscribe(topics)
        
        self.logger.info("Listening for MQTT messages... Press Ctrl+C to exit")
        self.client.loop_forever()
    
    def request_models_from_devices(self):
        """Request models from all connected devices"""
        request_command = {"command": "request_model"}
        self._send_command(json.dumps(request_command, separators=(',', ':')))
        self.logger.debug("Model request sent to devices")
    
    def check_alive_devices(self):
        """Check which devices are alive"""
        self.client.loop_stop()
        topics = [(self.TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)]
        self.client.subscribe(topics)
        
        self.logger.debug("Sending alive signal to devices")
        alive_command = {"command": "federate_alive"}

        self._send_command(json.dumps(alive_command, separators=(',', ':')))

        self.client.loop_forever()

        # while(True):
        #     self._send_command(json.dumps(alive_command, separators=(',', ':')))
        #     sleep(3)        
    
    def send_aggregated_weights(self):
        """Aggregate weights and send to devices"""
        self.aggregate_weights()
        # Send binary aggregated weights instead of JSON
        aggregated_binary_path = os.path.join(WEIGHTS_FOLDER, "aggregated_weights.nn")
        self._send_binary_file(aggregated_binary_path)
    
    def parse_training_data(self, folder=None):
        """Parse training data and generate visualizations"""
        parse_folder = folder if folder else PARSE_FOLDER
        metrics_folder = os.path.join(parse_folder, 'metrics/') if folder else METRICS_FOLDER
        do_parse(parse_folder, metrics_folder)

    def parse_all_training_data(self, base_folder=None):
        """Parse all the training data and generate all it's visualizations"""
        search_folder = base_folder if base_folder else PARSE_ALL_FOLDER
        for root, dirs, files in os.walk(search_folder, topdown=False):
            for name in files:
                if name.endswith('done.json'):
                    folder = os.path.dirname(os.path.join(root, name))
                    metrics = os.path.join(folder, 'metrics/')
                    self.logger.debug(f"Processing folder: {folder}")
                    do_parse(folder, metrics)
    
    def disconnect(self):
        """Disconnect MQTT client"""
        self.client.disconnect()
        self.logger.debug("MQTT client disconnected")

    def start_parent_aggregation_only(self, aggregation_config = {}):
        """Start aggregation-only mode with given configuration"""
        self.logger.info("Starting Aggregation-Only Mode")
        
        # Setup MQTT subscriptions
        topics = [
            (self.TOPIC_RECEIVE_FROM_DEVICES, 0),
            (self.TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (self.TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
        
        if self.hierarchical_config["enabled"]:
            topics.extend([
                (self.TOPIC_RECEIVE_COMMANDS_FROM_PARENT, 0),
                (self.TOPIC_RECEIVE_FROM_PARENT_RAW, 0),
                (self.TOPIC_RECEIVE_FROM_PARENT, 0)
            ])
            self.join_parent()
            
        self.client.subscribe(topics)
        self.client.loop_start()
        
        self.logger.info("Aggregation-Only Mode is now active")
        
        # Load aggregation configuration
        self.state.is_federated = True
        self.state.federated_path = aggregation_config.get("federated_path", WEIGHTS_FOLDER)
        os.makedirs(self.state.federated_path, exist_ok=True)
        
        self.logger.info(f"Aggregation path: {self.state.federated_path}")
        
        # Initialize state for aggregation
        self.state.current_round = 0
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        test_name = aggregation_config.get("name", "aggregation_only")
        
        # Override federated path to be unique for this run
        self.state.federated_path = os.path.join(self.state.federated_path, f"{timestamp}_{test_name}")
        os.makedirs(self.state.federated_path, exist_ok=True)
        os.makedirs(os.path.join(self.state.federated_path, str(self.state.current_round)), exist_ok=True)

        self.logger.info(f"Aggregation session path: {self.state.federated_path}")

        # Wait for client connections (Child Aggregators)
        self.logger.debug(f"Waiting {CONNECTION_WAIT_TIME}s for child aggregator connections")

        # 1. Ask everyone to unsubscribe from any previous session
        for i in range(COMMAND_RETRIES):
            unsub_command = {"command": "federate_unsubscribe"}
            self._send_command(json.dumps(unsub_command, separators=(',', ':')))
            sleep(COMMAND_RETRY_INTERVAL)
        
        # 2. Ask everyone to join this session
        for i in range(COMMAND_RETRIES):
            join_command = {"command": "federate_join"}
            self._send_command(json.dumps(join_command, separators=(',', ':')))
            sleep(COMMAND_RETRY_INTERVAL)
        
        # Wait for devices to respond to join command (they'll populate federated_clients)
        sleep(2)
        
        self.logger.info(f"Aggregation session started with {len(self.state.federated_clients)} child aggregators "
                       f"({len(self.state.connected_clients)} total connected)")
        
        # 3. Send Start Command
        self.fire_event("on_federation_started")
        # Note: In hierarchical mode, we trust that child aggregators already have their
        # NN configuration (layers, etc) set up, or they will receive it from their own config.
        # However, we still send a start command to signal the beginning of the process.
        # We pass minimal config to satisfy protocol if needed.
        config_dict = aggregation_config.get("config", {
             "layers": DEFAULT_LAYERS, # Default or placeholder
             "actvFunctions": DEFAULT_ACTIVATION_FUNCTIONS,
             "epochs": DEFAULT_EPOCHS,
             "learningRateOfWeights": DEFAULT_LEARNING_RATE_WEIGHTS,
             "learningRateOfBiases": DEFAULT_LEARNING_RATE_BIASES,
             "randomSeed": DEFAULT_RANDOM_SEED,
             "jsonWeights": DEFAULT_SEND_JSON_WEIGHTS
        }).copy()
        
        sliding_window = self.hierarchical_config.get("sliding_window")
        if sliding_window is not None and sliding_window != "":
            try:
                config_dict["sliding_window"] = int(sliding_window)
            except ValueError:
                pass
        
        start_command = {
            "command": "federate_start",
            "config": config_dict
        }
        
        # Set max rounds to infinite (or very large) if not specified, 
        # but for safety we can just track rounds indefinitely.
        self.state.max_rounds = 999999999
        
        # Update federated clients that joined to Training/Waiting status
        for client_id in self.state.federated_clients:
            self.state.federated_clients[client_id]['progress'] = 'Waiting' 
            self.state.federated_clients[client_id]['last_update'] = time.time()
        
        self.state.active_config = start_command.get("config")
        self._send_command(json.dumps(start_command, separators=(',', ':')))
        
        # Save configuration
        self._save_federated_config(start_command, {"name": test_name})

        # Run loop
        try:
            self._run_single_test_loop()
            
        except Exception as e:
            self.logger.error(f"Error in aggregation loop: {e}")
            traceback.print_exc()
            
        except KeyboardInterrupt:
            self.logger.info("Stopping Aggregation-Only Mode")

        finally:
            self.client.loop_stop()
            self._cleanup_federated_learning()

    def start_batch_federated_learning(self, batch_config_path, expected_clients=None):
        """Start batch federated learning process from JSON configuration file"""
        self.logger.info("Starting Batch Federated Learning")
        
        # Load batch configuration
        try:
            batch_config_path = self._resolve_batch_config_path(batch_config_path)
            with open(batch_config_path, 'r') as f:
                batch_config = json.load(f)
        except FileNotFoundError:
            self.logger.error(f"Configuration file not found: {batch_config_path}")
            return
        except json.JSONDecodeError as e:
            self.logger.error(f"Error decoding JSON: {e}")
            return
        
        if not isinstance(batch_config, list):
            self.logger.error("Configuration must be a list of test objects")
            return
        
        # Create batch-specific folder
        batch_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        batch_folder_name = f"batch_{batch_timestamp}"
        batch_base_path = os.path.join(WEIGHTS_FOLDER, batch_folder_name)
        os.makedirs(batch_base_path, exist_ok=True)
        self.state.batch_base_path = batch_base_path
        
        self.logger.info(f"Batch folder: {batch_base_path}")
        
        # Setup MQTT subscriptions
        topics = [
            (self.TOPIC_RECEIVE_FROM_DEVICES, 0),
            (self.TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (self.TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
        
        if self.hierarchical_config["enabled"]:
            topics.extend([
                (self.TOPIC_RECEIVE_COMMANDS_FROM_PARENT, 0),
                (self.TOPIC_RECEIVE_FROM_PARENT_RAW, 0),
                (self.TOPIC_RECEIVE_FROM_PARENT, 0)
            ])
            self.join_parent()
            
        self.client.subscribe(topics)
        self.client.loop_start()
        
        self.logger.info(f"Starting batch processing of {len(batch_config)} configurations")
        
        # Update state with batch info
        self.state.total_tests = len(batch_config)
        
        # Process each test configuration sequentially
        successful_tests = 0
        failed_tests = 0
        
        for test_index, test_config in enumerate(batch_config):
            sleep(3)

            self.state.current_test_index = test_index + 1
            self.state.current_test_name = test_config.get('name', f'Test {test_index + 1}')
            
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"STARTING TEST {test_index + 1} of {len(batch_config)}")
            self.logger.info(f"{'='*60}")
            
            # Validate test configuration
            if not self._validate_test_config(test_config, test_index + 1):
                self.logger.error(f"Test {test_index + 1} failed validation. Continuing to next test.")
                failed_tests += 1
                continue
            
            # Run single federated learning session
            success = self._run_single_batch_test(test_config, test_index + 1, expected_clients, batch_base_path)
            
            if not success:
                self.logger.error(f"Test {test_index + 1} failed.")
                failed_tests += 1
                # If stop was requested, break out of batch loop
                if self.state.stop_requested:
                    self.logger.debug("Stopping batch processing due to stop request")
                    break
                self.logger.debug("Continuing to next test")
            else:
                self.logger.info(f"Test {test_index + 1} completed successfully.")
                successful_tests += 1
            
            # Wait between tests if not the last one
            if test_index < len(batch_config) - 1:
                self.logger.debug("Waiting 5 seconds before next test")
                # Check for stop during wait
                for _ in range(5):
                    if self.state.stop_requested:
                        self.logger.debug("Stop requested during wait between tests")
                        break
                    sleep(1)
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info("BATCH PROCESSING COMPLETED")
        self.logger.info(f"{'='*60}")
        self.logger.info("Test summary:")
        self.logger.info(f"   Successful tests: {successful_tests}")
        self.logger.info(f"   Failed tests: {failed_tests}")
        self.logger.info(f"   Total tests: {len(batch_config)}")
        self.logger.info(f"   Batch folder: {batch_base_path}")
        
        # Create batch summary file
        batch_summary = {
            "batch_started": batch_timestamp,
            "batch_completed": datetime.now().isoformat(),
            "total_tests": len(batch_config),
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "batch_folder": batch_folder_name,
            "config_file": batch_config_path,
            "tests": []
        }
        
        # Add test details to summary
        for i, test_config in enumerate(batch_config):
            test_info = {
                "test_number": i + 1,
                "name": test_config.get('name', f'batch_test_{i + 1}'),
                "epochs": test_config['epochs'],
                "rounds": test_config.get('rounds', 1),
                "layers": test_config['layers'],
                "seed": test_config['seed']
            }
            dataset_selection = self._build_dataset_selection(test_config)
            if dataset_selection:
                test_info.update(dataset_selection)
            batch_summary["tests"].append(test_info)
        
        # Save batch summary
        summary_path = os.path.join(batch_base_path, "batch_summary.json")
        with open(summary_path, 'w') as f:
            json.dump(batch_summary, f, indent=4, separators=(',', ':'))
        
        if successful_tests > 0:
            self.logger.info(f"Batch processing completed with {successful_tests} successful test(s).")
        else:
            self.logger.error("No tests were successful.")
        
        self.logger.info(f"Summary saved to: {summary_path}")
        
        # Final cleanup
        self._cleanup_federated_learning()
    
    def start_interval_federated_learning(self, config_file, interval_seconds, rounds_per_interval, delay_between_rounds, total_intervals=None, expected_clients=None):
        """Start interval-based federated learning process"""
        self.logger.info("Starting Interval-Based Federated Learning")

        # Load batch configuration
        if not config_file:
            config = {
                "epochs": DEFAULT_EPOCHS,
                "layers": DEFAULT_LAYERS,
                "activationFunctions": DEFAULT_ACTIVATION_FUNCTIONS,
                "learningRateWeights": DEFAULT_LEARNING_RATE_WEIGHTS,
                "learningRateBiases": DEFAULT_LEARNING_RATE_BIASES,
                "seed": DEFAULT_RANDOM_SEED,
                "sendJsonWeights": DEFAULT_SEND_JSON_WEIGHTS
            }
            self.logger.info("No configuration file specified. Using default/placeholder hyperparameters.")
        else:
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
            except FileNotFoundError:
                self.logger.error(f"Configuration file not found: {config_file}")
                return
            except json.JSONDecodeError as e:
                self.logger.error(f"Error decoding JSON: {e}")
                return
        
        if not isinstance(config, dict):
            self.logger.error("Configuration must be a test dict")
            return
        
        if rounds_per_interval is None or not isinstance(rounds_per_interval, int) or rounds_per_interval <= 0:
            self.logger.error("rounds_per_interval must be a positive integer")
            return
        
        if interval_seconds is None or not isinstance(interval_seconds, int) or interval_seconds <= 0:
            self.logger.error("interval_seconds must be a positive integer")
            return
        
        if delay_between_rounds is None or not isinstance(delay_between_rounds, int) or delay_between_rounds < 0:
            self.logger.error("delay_between_rounds must be a non-negative integer")
            return

        # Create batch-specific folder
        folder_name = f"interval_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}"
        base_path = os.path.join(WEIGHTS_FOLDER, folder_name)
        os.makedirs(base_path, exist_ok=True)
        self.state.base_path = base_path
        
        self.logger.info(f"Base path folder: {base_path}")
        
        # Setup MQTT subscriptions
        topics = [
            (self.TOPIC_RECEIVE_FROM_DEVICES, 0),
            (self.TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (self.TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
        
        if self.hierarchical_config["enabled"]:
            topics.extend([
                (self.TOPIC_RECEIVE_COMMANDS_FROM_PARENT, 0),
                (self.TOPIC_RECEIVE_FROM_PARENT_RAW, 0),
                (self.TOPIC_RECEIVE_FROM_PARENT, 0)
            ])
            self.join_parent()
            
        self.client.subscribe(topics)
        self.client.loop_start()

        test_index = 0

        interval_config = {
            "interval_seconds": interval_seconds,
            "rounds_per_interval": rounds_per_interval,
            "total_intervals": total_intervals,
            "delay_between_rounds": delay_between_rounds
        }

        while True:
            # Check if total intervals reached
            if total_intervals is not None and test_index >= total_intervals:
                self.logger.info(f"Completed {test_index} intervals. Stopping.")
                break

            # Run single federated learning session
            success = self._run_single_batch_test(config, test_index + 1, expected_clients, base_path, interval_config)
            
            if self.state.stop_requested:
                self.logger.debug("Stopping processing due to stop request")
                break

            if not success:
                self.logger.error(f"Interval training #{test_index + 1} failed. Ending federative process.")
                break
            else:
                self.logger.info(f"Interval training #{test_index + 1} completed successfully.")
            
            test_index += 1

            # Wait for next interval if not stopping and (forever OR not reached limit)
            should_wait = not self.state.stop_requested
            if total_intervals is not None and test_index >= total_intervals:
                should_wait = False
            
            if should_wait:
                self.logger.info(f"Waiting {interval_seconds}s before next interval")
                # Wait in 1s increments to allow checking for stop signal
                wait_time = int(interval_seconds)
                for _ in range(wait_time):
                    if self.state.stop_requested:
                        break
                    sleep(1)
                
                # Handle fractional seconds if any
                if not self.state.stop_requested and interval_seconds > wait_time:
                    sleep(interval_seconds - wait_time)
        
        # Final cleanup
        self._cleanup_federated_learning()
        

    def _validate_test_config(self, test_config, test_number):
        """Validate individual test configuration"""
        required_fields = ['epochs', 'layers', 'activationFunctions', 'learningRateWeights', 'learningRateBiases', 'seed']
        
        for field in required_fields:
            if field not in test_config:
                self.logger.error(f"Test {test_number}: Required field '{field}' not found")
                return False
        
        # Validate layers and activation functions match
        layers = test_config['layers']
        activation_funcs = test_config['activationFunctions']
        
        if not isinstance(layers, list) or len(layers) < 2:
            self.logger.error(f"Test {test_number}: 'layers' must be a list with at least 2 elements")
            return False
        
        if not isinstance(activation_funcs, list) or len(activation_funcs) != len(layers) - 1:
            self.logger.error(f"Test {test_number}: 'activationFunctions' must have {len(layers) - 1} elements")
            return False
        
        # Validate numeric values
        if not isinstance(test_config['epochs'], int) or test_config['epochs'] < 1:
            self.logger.error(f"Test {test_number}: 'epochs' must be a positive integer")
            return False
        
        if not isinstance(test_config['learningRateWeights'], (int, float)) or test_config['learningRateWeights'] <= 0:
            self.logger.error(f"Test {test_number}: 'learningRateWeights' must be a positive number")
            return False
        
        if not isinstance(test_config['learningRateBiases'], (int, float)) or test_config['learningRateBiases'] <= 0:
            self.logger.error(f"Test {test_number}: 'learningRateBiases' must be a positive number")
            return False
        
        if not isinstance(test_config['seed'], int):
            self.logger.error(f"Test {test_number}: 'seed' must be an integer")
            return False

        for field in ('database', 'dataset', 'datasetKey', 'datasetBin', 'datasetMeta'):
            if field in test_config and not isinstance(test_config[field], str):
                self.logger.error(f"Test {test_number}: '{field}' must be a string when provided")
                return False
        
        return True

    def _resolve_batch_config_path(self, batch_config_path):
        """Resolve batch config paths relative to the server's batch-config folder."""
        if os.path.isabs(batch_config_path):
            return batch_config_path

        direct_path = os.path.abspath(batch_config_path)
        if os.path.exists(direct_path):
            return direct_path

        if os.path.dirname(batch_config_path):
            candidate = os.path.join(BATCH_CONFIG_FOLDER, batch_config_path)
        else:
            candidate = os.path.join(BATCH_CONFIG_FOLDER, os.path.basename(batch_config_path))

        return os.path.abspath(candidate)

    def _build_dataset_selection(self, test_config):
        """Extract optional dataset selection fields from a batch test config."""
        dataset = test_config.get('database') or test_config.get('dataset') or test_config.get('datasetKey')
        if not isinstance(dataset, str) or not dataset.strip():
            return {}

        selection = {'dataset': dataset.strip()}
        dataset_bin = test_config.get('datasetBin')
        dataset_meta = test_config.get('datasetMeta')
        if isinstance(dataset_bin, str) and dataset_bin.strip():
            selection['datasetBin'] = dataset_bin.strip()
        if isinstance(dataset_meta, str) and dataset_meta.strip():
            selection['datasetMeta'] = dataset_meta.strip()
        return selection
    
    def _run_single_batch_test(self, test_config, test_number, expected_clients, base_path=None, interval_config=None):
        """Run a single federated learning test from batch configuration"""
        original_enabled = self.hierarchical_config.get("enabled", False)
        self.state.parent_command_status = "pending"
        self.state.waiting_for_parent_start = False
        try:
            # Initialize federated learning state for this test
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            test_name = ""
            if interval_config is not None:
                test_name = f'interval_{test_number}'
            else:
                test_name = test_config.get('name', f'batch_test_{test_number}')
            
            # Use batch_base_path if provided (for batch mode), otherwise use WEIGHTS_FOLDER (for single mode)
            if base_path:
                self.state.federated_path = os.path.join(base_path, f"{timestamp}_{test_name}")
            else:
                self.state.federated_path = os.path.join(WEIGHTS_FOLDER, f"{timestamp}_{test_name}")
            self.state.current_round = 0
            self.state.is_federated = True
            # Clear federated clients to start fresh for this test
            self.state.federated_clients.clear()
            # Don't clear connected_clients - keep tracking all devices
            # self.state.connected_clients.clear()
            
            # Extract configuration
            max_rounds = 0
            if interval_config is not None:
                max_rounds = interval_config['rounds_per_interval']
            else:
                max_rounds = test_config.get('rounds', 1)  # Default to 1 round if not specified
            
            self.logger.info(f"⚙️ Test {test_number} configuration: {test_name}")
            self.logger.info(f"   Epochs: {test_config['epochs']}, Rounds: {max_rounds}")
            self.logger.info(f"   Layers: {test_config['layers']}")
            if self.debug:
                self.logger.debug(f"   Activation functions: {test_config['activationFunctions']}")
                self.logger.debug(f"   LR weights: {test_config['learningRateWeights']}, LR bias: {test_config['learningRateBiases']}")
                self.logger.debug(f"   Seed: {test_config['seed']}, JSON weights: {test_config.get('sendJsonWeights', False)}")
            
            # Create directories
            os.makedirs(self.state.federated_path, exist_ok=True)
            os.makedirs(os.path.join(self.state.federated_path, str(self.state.current_round)), exist_ok=True)
            
            # Wait for client connections
            self.logger.debug(f"Waiting {CONNECTION_WAIT_TIME}s for device connections")

            for i in range(COMMAND_RETRIES):
                unsub_command = {"command": "federate_unsubscribe"}
                self._send_command(json.dumps(unsub_command, separators=(',', ':')))
                sleep(COMMAND_RETRY_INTERVAL)
            
            for i in range(COMMAND_RETRIES):
                join_command = {"command": "federate_join"}
                self._send_command(json.dumps(join_command, separators=(',', ':')))
                sleep(COMMAND_RETRY_INTERVAL)
            
            # If expected_clients is not specified (blank/None), calculate expected_clients dynamically
            # based on which clients from the last test are still active on the network.
            if expected_clients is None or expected_clients <= 0:
                if hasattr(self.state, 'last_active_clients') and self.state.last_active_clients:
                    # Filter last active clients by checking if they are still alive (seen in last 45 seconds)
                    alive_last_active = [cid for cid in self.state.last_active_clients
                                         if cid in self.state.connected_clients and
                                         time.time() - self.state.connected_clients[cid].get('last_seen', 0) < 45]
                    
                    if len(alive_last_active) >= 1:
                        expected_clients = len(alive_last_active)
                        self.logger.info(
                            f"Test {test_number}: Dynamically expected clients: {expected_clients} "
                            f"(alive from previous test: {alive_last_active})"
                        )

            if len(self.state.federated_clients) < 1:
                self.logger.error(f"Test {test_number}: No clients joined federation")
                return False
            
            if expected_clients and len(self.state.federated_clients) < expected_clients:
                self.logger.error(f"Test {test_number}: {len(self.state.federated_clients)}/{expected_clients} clients joined (insufficient)")
                self._send_unsubscribe_command()
                return False
            
            self.logger.info(f"Test {test_number} started with {len(self.state.federated_clients)} federated clients "
                           f"({len(self.state.connected_clients)} total connected)")
            
            self.fire_event("on_federation_started")
            
            # Create start command with test-specific configuration
            start_command = {
                "command": "federate_start",
                "config": {
                    "layers": test_config['layers'],
                    "actvFunctions": test_config['activationFunctions'],
                    "epochs": test_config['epochs'],
                    "learningRateOfWeights": test_config['learningRateWeights'],
                    "learningRateOfBiases": test_config['learningRateBiases'],
                    "randomSeed": test_config['seed'],
                    "jsonWeights": test_config.get('sendJsonWeights', DEFAULT_SEND_JSON_WEIGHTS)
                }
            }
            
            sliding_window = self.hierarchical_config.get("sliding_window")
            if sliding_window is not None and sliding_window != "":
                try:
                    start_command["config"]["sliding_window"] = int(sliding_window)
                except ValueError:
                    pass
            start_command.update(self._build_dataset_selection(test_config))
            
            self.state.max_rounds = max_rounds
            
            # Update federated clients that joined to Training status
            # Note: federated_clients is now populated by join commands, not copied from connected_clients
            for client_id in self.state.federated_clients:
                self.state.federated_clients[client_id]['round'] = 1
                self.state.federated_clients[client_id]['progress'] = 'Training'
                self.state.federated_clients[client_id]['received_json'] = False
                self.state.federated_clients[client_id]['received_nn'] = False
                self.state.federated_clients[client_id]['last_update'] = time.time()
            
            self.state.active_config = start_command.get("config")
            
            # If wait_for_parent_start is enabled, pause here until parent aggregator releases the gate
            if original_enabled and self.hierarchical_config.get("wait_for_parent_start", True):
                status = getattr(self.state, 'parent_command_status', 'pending')
                
                if status == "started":
                    self.logger.info("Parent start signal already received. Proceeding to local training!")
                elif status == "canceled":
                    self.logger.warning("Parent aggregator already aborted/ended the session. Skipping start wait.")
                    if self.hierarchical_config.get("continue_on_parent_abort", True):
                        self.logger.warning("Falling back to standalone/local training.")
                        self.hierarchical_config["enabled"] = False
                    else:
                        return False
                else:
                    self.logger.info("Waiting for federate_start command from parent aggregator before starting local training...")
                    self.state.waiting_for_parent_start = True
                    
                    # Resend join command just in case (though join_parent was already triggered by parent's federate_join)
                    self.join_parent()
                    
                    # Wait in a loop until released or stopped
                    while self.state.waiting_for_parent_start and not self.state.stop_requested:
                        sleep(0.5)
                    
                    if self.state.stop_requested:
                        self.logger.info("Stop requested while waiting for parent aggregator. Aborting test.")
                        return False
                        
                    final_status = getattr(self.state, 'parent_command_status', 'pending')
                    if final_status != "started":
                        # If parent aborted, check if we should continue locally/standalone or fail
                        if self.hierarchical_config.get("continue_on_parent_abort", True):
                            self.logger.warning("Parent aggregator aborted or disconnected. Falling back to standalone/local training.")
                            # Temporarily disable hierarchical mode for this test so we proceed without parent
                            self.hierarchical_config["enabled"] = False
                        else:
                            self.logger.error("Parent aggregator aborted the session. Skipping this test.")
                            return False
                    else:
                        self.logger.info("Received parent start signal. Starting local training!")

            self._send_command(json.dumps(start_command, separators=(',', ':')))
            
            # Save configuration with batch test info
            self._save_federated_config(start_command, test_config, test_number)
            
            # Run federated learning loop for this test
            delay = 0
            if interval_config is not None:
                delay = interval_config.get('delay_between_rounds', 0)
            
            success = self._run_single_test_loop(delay_between_rounds=delay)
            
            if success:
                # Finalize this test
                self._finalize_single_batch_test()
            else:
                # Mark test as failed but save partial results
                failed_path = os.path.join(self.state.federated_path, "failed.json")
                with open(failed_path, 'w') as f:
                    json.dump({
                        "failed_at": datetime.now().isoformat(),
                        "test_number": test_number,
                        "last_round": self.state.current_round
                    }, f, indent=4, separators=(',', ':'))
            
            return success
            
        except Exception as e:
            self.logger.error(f"Unexpected error in test {test_number}: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Restore original hierarchical enabled status
            if 'original_enabled' in locals():
                self.hierarchical_config["enabled"] = original_enabled
            # Ensure cleanup happens even if test fails
            try:
                self._send_unsubscribe_command()
                sleep(2)  # Give time for cleanup
            except:
                pass  # Ignore cleanup errors
    
    def _run_single_test_loop(self, delay_between_rounds=0):
        """Run federated learning loop for a single batch test"""
        status_timer = 0
        round_start_time = time.time()
        
        while True:
            sleep(1)
            
            # Remove inactive client aggregators/devices (no ping in last 90s)
            for client_id in list(self.state.federated_clients.keys()):
                last_seen = self.state.connected_clients.get(client_id, {}).get('last_seen', 0)
                if time.time() - last_seen > 90:
                    self.logger.warning(f"Client {client_id} is inactive (no communication for 90s). Removing from federation.")
                    del self.state.federated_clients[client_id]

            # self.logger.debug(f"Loop tick. Waiting: {len(self.state.waiting_for_clients)}")
            status_timer += 1
            
            # Check if stop was requested
            if self.state.stop_requested:
                break
            
            # Check if all clients have submitted their models
            if len(self.state.waiting_for_clients) == 0 or (self.max_wait_time and time.time() - round_start_time >= self.max_wait_time):
                if self.state.max_rounds and self.state.max_rounds < 999999999 and self.state.current_round + 1 > self.state.max_rounds:
                    self.logger.info(f"Round {self.state.current_round}/{self.state.max_rounds} complete - last round!")
                    self.aggregate_weights(self.state.current_round)
                    break

                # If round_finished event returns False (e.g. from synchronous strategy waiting for parent), continue waiting
                event_result = self.fire_event("round_finished", {"round": self.state.current_round})
                if event_result is False:
                    continue
                
                max_r_str = f"/{self.state.max_rounds}" if (self.state.max_rounds and self.state.max_rounds < 999999999) else ""
                self.logger.info(f"Round {self.state.current_round}{max_r_str} complete - {len(self.state.federated_clients) - len(self.state.waiting_for_clients)}/{len(self.state.federated_clients)} models received")
                sleep(1)
                
                # Aggregate weights and send to clients
                result = self.aggregate_weights(self.state.current_round)
                if result is None:
                    self.logger.error("Failed to aggregate weights for this test.")
                    return False

                # Delay between rounds if configured
                if delay_between_rounds > 0:
                    self.logger.info(f"Waiting {delay_between_rounds}s before next round...")
                    initial_time = time.time()
                    while time.time() - initial_time < delay_between_rounds:
                        if self.state.stop_requested:
                            break
                        sleep(1)
                
                # Send binary aggregated weights to devices (unless paused)
                aggregated_binary_path = os.path.join(
                    self.state.federated_path,
                    str(self.state.current_round),
                    "aggregated_weights.nn"
                )
                
                if self.state.is_paused:
                    self.state.paused_aggregated_path = aggregated_binary_path
                    self.logger.info("Training paused - weights aggregated but not sent")
                    # Wait until resumed (or stopped)
                    while self.state.is_paused and not self.state.stop_requested:
                        sleep(0.5)
                    
                    # Check if stopped while paused
                    if self.state.stop_requested:
                        break
                    
                    self.logger.info("Training resumed - sending aggregated weights")
                
                # Prepare for next round BEFORE sending weights to clients to avoid race conditions
                self.state.current_round += 1
                next_round_dir = os.path.join(self.state.federated_path, str(self.state.current_round))
                os.makedirs(next_round_dir, exist_ok=True)
                
                # Reset all federated clients for new round
                for client_id in self.state.federated_clients:
                    self.state.federated_clients[client_id]['round'] = self.state.current_round
                    self.state.federated_clients[client_id]['progress'] = 'Training'
                    self.state.federated_clients[client_id]['received_json'] = False
                    self.state.federated_clients[client_id]['received_nn'] = False
                    self.state.federated_clients[client_id]['last_update'] = time.time()
                
                self.logger.debug(f"Starting round {self.state.current_round}")
                
                self._send_binary_file(aggregated_binary_path)
                self.logger.debug("Weights sent.")
                sleep(1)
                status_timer = 0

            elif status_timer == STATUS_UPDATE_INTERVAL - 5:
                self._send_command(json.dumps({"command": "federate_alive"}, separators=(',', ':')))
                
            elif status_timer >= STATUS_UPDATE_INTERVAL:
                waiting = sorted(self.state.waiting_for_clients)
                received_count = len(self.state.federated_clients) - len(waiting)
                total_count = len(self.state.federated_clients)
                
                # Count alive devices (seen in last 35 seconds)
                alive_count = sum(1 for info in self.state.connected_clients.values() 
                                 if time.time() - info['last_seen'] < 35)

                self.logger.info(f"Status: {received_count}/{total_count} received | Waiting: {waiting} | Alive: {alive_count}")
                status_timer = 0
        
        # Check if loop was broken due to stop request
        if self.state.stop_requested:
            max_r_str = f"/{self.state.max_rounds}" if (self.state.max_rounds and self.state.max_rounds < 999999999) else ""
            self.logger.info(f"Stop requested - ending round {self.state.current_round}{max_r_str}")
            self.logger.debug("Sending unsubscribe command to devices")
            self._send_unsubscribe_command()
            sleep(2)  # Give time for devices to receive and process
            return False
        
        return True
    
    def _finalize_single_batch_test(self):
        """Finalize a single batch test"""
        # Save last active clients
        self.state.last_active_clients = list(self.state.federated_clients.keys())
        
        # Create final round directory
        self.state.current_round += 1
        final_round_dir = os.path.join(self.state.federated_path, str(self.state.current_round))
        os.makedirs(final_round_dir, exist_ok=True)
        
        # Send end command
        end_command = {"command": "federate_end"}
        self._send_command(json.dumps(end_command, separators=(',', ':')))
        sleep(3)  # Shorter wait between batch tests
        
        # Mark all federated clients as completed
        for client_id in self.state.federated_clients:
            self.state.federated_clients[client_id]['progress'] = 'Completed'
            self.state.federated_clients[client_id]['last_update'] = time.time()
        
        # Mark completion
        done_path = os.path.join(self.state.federated_path, "done.json")
        with open(done_path, 'w') as f:
            json.dump({"completed_at": datetime.now().isoformat()}, f, indent=4, separators=(',', ':'))

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='MQTT Federated Server')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Alive command
    alive_parser = subparsers.add_parser('alive', help='Check alive devices')
    
    # Federate command
    federate_parser = subparsers.add_parser('federate', help='Start federated learning')
    federate_parser.add_argument('--rounds', '-r', type=int, required=True,
                                help='Number of federated learning rounds')
    federate_parser.add_argument('--clients', '-c', type=int, required=True,
                                help='Number of expected clients')
    
    # Batch command
    batch_parser = subparsers.add_parser('batch', help='Start batch federated learning from JSON config')
    batch_parser.add_argument('--config', '-f', type=str, required=True,
                             help='Path to JSON configuration file')
    batch_parser.add_argument('--clients', '-c', type=int,
                             help='Number of expected clients (optional)')
    
    # Parse command
    parse_parser = subparsers.add_parser('parse', help='Parse training data and generate visualizations')
    parse_parser.add_argument('--folder', '-f', type=str,
                             help='Specific folder to parse (optional, uses default if not provided)')
    
    # ParseAll command
    parseall_parser = subparsers.add_parser('parseall', help='Parse all training data and generate all visualizations')
    parseall_parser.add_argument('--folder', '-f', type=str,
                                help='Base folder to search for training data (optional, uses default if not provided)')
    
    # BatchCompare command
    batchcompare_parser = subparsers.add_parser('batchcompare', help='Compare metrics across multiple batch test results')
    batchcompare_parser.add_argument('--batch-folder', '-b', type=str, required=True,
                                    help='Path to batch folder containing test results')
    batchcompare_parser.add_argument('--output', '-o', type=str,
                                    help='Output folder for comparison plots (optional)')
    
    # Unsub command
    unsub_parser = subparsers.add_parser('unsub', help='Send unsubscribe command to clients')
    
    return parser.parse_args()


def main():
    """Main application entry point"""
    # Parse command line arguments
    args = parse_arguments()
    
    try:
        # If command line arguments are provided, execute directly
        if args.command:
            # CLI mode - enable stdout logging
            server = MQTTFederatedServer(debug=False, enable_stdout=True)

            if args.command == 'alive':
                print("Executing 'alive' command")
                server.check_alive_devices()
                
            elif args.command == 'federate':
                print(f"Starting federated server with {args.rounds} rounds and {args.clients} expected clients")
                server.start_federated_learning(max_rounds=args.rounds, expected_clients=args.clients)
                
            elif args.command == 'batch':
                print(f"Starting batch processing using configuration: {args.config}")
                if args.clients:
                    print(f"Expecting {args.clients} clients")
                server.start_batch_federated_learning(args.config, expected_clients=args.clients)
                
            elif args.command == 'parse':
                print("Processing training data and generating visualizations")
                if args.folder:
                    print(f"Using specified folder: {args.folder}")
                server.parse_training_data(args.folder)
                
            elif args.command == 'parseall':
                print("Processing all training data and generating all visualizations")
                if args.folder:
                    print(f"Searching data in folder: {args.folder}")
                server.parse_all_training_data(args.folder)
                
            elif args.command == 'batchcompare':
                print("Comparing metrics between batch tests")
                batch_folder = args.batch_folder
                output_folder = args.output if args.output else None
                
                plot_batch_comparison(batch_folder, output_folder)
                if output_folder:
                    print(f"Comparison complete! Graphs saved to: {output_folder}")
                else:
                    print(f"Comparison complete! Graphs saved to: {os.path.join(batch_folder, 'metrics')}")
                
            elif args.command == 'unsub':
                print("Sending unsubscribe command")
                server._send_unsubscribe_command()
                sleep(2)  # Give time for the command to be sent
                
            return  # Exit after executing the command
        
        # If no command line arguments, show usage message
        print("No command provided. Use --help to see available commands.")
        print("For interactive mode, use the TUI: python -m atlantico_server.tui_runner")
                
    except KeyboardInterrupt:
        print("\nExiting")


if __name__ == "__main__":
    main()