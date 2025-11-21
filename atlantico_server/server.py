"""Main server implementation (renamed from `novoServidor.py`).

This module contains the full MQTT federated server implementation. The
original `novoServidor.py` top-level script has been removed to avoid
duplication; use `python server.py` from the repo root or run
`python -m atlantico_server.server` to execute the CLI.
"""

import json
import logging
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
from .logging import setup_logging, get_logger

# Global configuration constants
BROKER_IP = os.getenv("MQTT_BROKER_HOST", "127.0.0.1")
BROKER_PORT = 1883
BROKER_KEEPALIVE = 60

# MQTT Topics
TOPIC_RECEIVE_FROM_DEVICES = "esp32/fl/model/push"
TOPIC_RECEIVE_FROM_DEVICES_RAW = "esp32/fl/model/rawpush/+"
TOPIC_SEND_TO_DEVICES = "esp32/fl/model/pull"
TOPIC_SEND_TO_DEVICES_RAW = "esp32/fl/model/rawpull"
TOPIC_RECEIVE_COMMANDS_FROM_DEVICES = "esp32/fl/commands/push"
TOPIC_SEND_COMMANDS_TO_DEVICES = "esp32/fl/commands/pull"
TOPIC_RESUME_TO_DEVICES = "esp32/fl/model/resume"
TOPIC_RESUME_TO_DEVICES_RAW = "esp32/fl/model/rawresume"

# Directory paths
PARSE_FOLDER = "parse/"
PARSE_ALL_FOLDER = "parse_all/"
WEIGHTS_FOLDER = "weights/"
METRICS_FOLDER = "metrics/"

# Federated learning configuration
DEFAULT_LAYERS = [3, 400, 300, 200, 100, 6]
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
COMMAND_RETRY_INTERVAL = 3
COMMAND_RETRIES = 1
STATUS_UPDATE_INTERVAL = 30


class FederatedServerState:
    """Class to manage federated server state"""
    
    def __init__(self):
        self.is_federated = False
        self.federated_path = ""
        self.current_round = 0
        self.max_rounds = 0
        self.connected_clients = {}  # {device_id: {'last_seen': timestamp}}
        self.federated_clients = {}  # {device_id: {'round': int, 'progress': str, 'last_update': timestamp}}
        self.debug = False
        self.is_paused = False
        self.paused_aggregated_path: str | None = None  # Store path to aggregated weights when paused
        self.stop_requested = False  # Flag to gracefully stop federated learning
    
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


class MQTTFederatedServer:
    """Main federated learning server class"""
    
    def __init__(self, debug=False, enable_stdout=True):
        # Use a short, human-friendly id suffix (8 hex chars) for broker logs
        short_id = uuid.uuid4().hex[:8]
        self.client = mqtt.Client(client_id=f"Aggregrator-{short_id}", clean_session=True)
        self.state = FederatedServerState()
        self._setup_mqtt_client()
        self.debug = debug
        
        # Setup logging (file always, stdout optional)
        self.logger = setup_logging(debug=debug, enable_stdout=enable_stdout)
        
    def _setup_mqtt_client(self):
        """Configure MQTT client"""
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(BROKER_IP, BROKER_PORT, BROKER_KEEPALIVE)
        
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc != 0:
            self.logger.error(f"MQTT connection failed with code: {rc}")
            
    def _on_message(self, client, userdata, message):
        """MQTT message callback"""
        try:
            topic = message.topic
            topic_parts = topic.split('/')
            if self.debug:
                self.logger.debug(f"Message received on topic: {topic}")
            
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
        
        # Update federated client progress
        json_filepath = filepath.replace(".nn", ".json")
        if os.path.exists(json_filepath) and client_name in self.state.federated_clients:
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
            elif command == "alive":
                self._handle_alive_command(client_id)
            else:
                self.logger.warning(f"Unrecognized command: {payload}")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Processing command: {e}")
    
    def _handle_federated_command(self, command, client_id, command_data):
        """Handle federated learning specific commands"""
        if command == "join":
            self._handle_join_command(client_id)
        elif command == "leave":
            self._handle_leave_command(client_id)
        elif command == "resume":
            self._handle_resume_command(client_id)
        elif command == "alive":
            # In federated mode, only track already-joined devices (no auto-discovery)
            if client_id in self.state.connected_clients:
                self._handle_alive_command(client_id, auto_discover=False)
    
    def _handle_join_command(self, client_id):
        """Handle client join requests"""
        if client_id not in self.state.connected_clients:
            self.state.connected_clients[client_id] = {'last_seen': time.time()}
            self.logger.info(f"Client {client_id} joined the server. "
                      f"Total clients: {len(self.state.connected_clients)}")
    
    def _handle_leave_command(self, client_id):
        """Handle client leave notifications"""
        if client_id in self.state.connected_clients:
            del self.state.connected_clients[client_id]
            self.logger.info(f"Client {client_id} left the server")
    
    def _handle_resume_command(self, client_id):
        """Handle client resume notifications"""
        if client_id in self.state.connected_clients:
            self.logger.info(f"Client {client_id} is ready to continue")
            try:
                resume_command = {
                    "command": "federate_resume",
                    "client": client_id,
                    "round": self.state.current_round
                }
                self._send_command(json.dumps(resume_command, separators=(',', ':')))
                
                # Try to send binary .nn file first, fallback to JSON
                aggregated_binary_path = os.path.join(
                    self.state.federated_path,
                    str(self.state.current_round - 1),
                    "aggregated_weights.nn"
                )
                
                if os.path.exists(aggregated_binary_path):
                    self.logger.debug(f"Sending binary resume file to {client_id}")
                    self._send_binary_file(aggregated_binary_path, f"{TOPIC_RESUME_TO_DEVICES_RAW}/{client_id}")
                else:
                    # Fallback to JSON if binary file doesn't exist
                    aggregated_json_path = os.path.join(
                        self.state.federated_path,
                        str(self.state.current_round - 1),
                        "aggregated_weights.json"
                    )
                    self.logger.debug(f"Binary file not found, sending JSON to {client_id}")
                    self._send_file(aggregated_json_path, TOPIC_RESUME_TO_DEVICES)
                
            except Exception as e:
                self.logger.error(f"Sending weights file: {e}")
    
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

            # Update federated client progress if NN file exists
            nn_filepath = filepath.replace(".json", ".nn")
            if os.path.exists(nn_filepath) and client_name in self.state.federated_clients:
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
    
    def _send_command(self, command_data, topic=TOPIC_SEND_COMMANDS_TO_DEVICES):
        """Send command via MQTT"""
        try:
            if self.debug:
                self.logger.debug("Sending command via MQTT")
            self.client.publish(topic, command_data)
        except Exception as e:
            self.logger.error(f"Sending command via MQTT: {e}")
    
    def _send_file(self, filepath, topic=TOPIC_SEND_TO_DEVICES):
        """Send file content via MQTT"""
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
    
    def _send_binary_file(self, filepath, topic=TOPIC_SEND_TO_DEVICES_RAW):
        """Send binary file content via MQTT"""
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
            return self._aggregate_weights_binary(source_dir, nn_files, round_number)
        else:
            # FALLBACK METHOD: Use JSON files if no .nn files found
            self.logger.warning("No .nn files found, trying JSON fallback method")
            json_files = [f for f in files if f.endswith('.json') and f != "aggregated_weights.json"]
            
            if json_files:
                self.logger.debug(f"Using JSON fallback method: {len(json_files)} JSON files found")
                return self._aggregate_weights_json(source_dir, json_files, round_number)
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

        # Verify all networks have the same structure
        first_network = networks[0]
        for i, network in enumerate(networks[1:], 1):
            if network['numberOflayers'] != first_network['numberOflayers']:
                self.logger.error(f"Different number of layers in file {nn_files[i]}")
                return None
            
            for layer_idx in range(network['numberOflayers']):
                first_layer = first_network['layers'][layer_idx]
                curr_layer = network['layers'][layer_idx]
                
                if (first_layer['inputs'] != curr_layer['inputs'] or
                    first_layer['outputs'] != curr_layer['outputs']):
                    self.logger.error(f"Different layer structure in file {nn_files[i]}")
                    return None
        
        # Create aggregated network structure
        aggregated_network = {
            'numberOflayers': first_network['numberOflayers'],
            'layers': []
        }
        
        # Aggregate each layer
        for layer_idx in range(first_network['numberOflayers']):
            first_layer = first_network['layers'][layer_idx]
            
            aggregated_layer = {
                'inputs': first_layer['inputs'],
                'outputs': first_layer['outputs'],
                'activation_function': first_layer['activation_function'],
                'biases': np.zeros(first_layer['outputs'], dtype=np.float32),
                'weights': np.zeros((first_layer['outputs'], first_layer['inputs']), dtype=np.float32)
            }
            
            # Sum all biases and weights
            for network in networks:
                layer = network['layers'][layer_idx]
                aggregated_layer['biases'] += layer['biases']
                aggregated_layer['weights'] += layer['weights']
            
            # Average the sums
            aggregated_layer['biases'] /= len(networks)
            aggregated_layer['weights'] /= len(networks)
            
            aggregated_network['layers'].append(aggregated_layer)
            if self.debug:
                self.logger.debug(f"Layer {layer_idx}: {aggregated_layer['inputs']} → {aggregated_layer['outputs']}")
        
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
        return output_path
    
    def start_federated_learning(self, max_rounds=None, expected_clients=None):
        """Start federated learning process"""
        self.logger.info("Starting Federated Learning")
        
        # Setup MQTT subscriptions
        topics = [
            (TOPIC_RECEIVE_FROM_DEVICES, 0),
            (TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
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
            "device_count": len(self.state.connected_clients),
            "bits": "32",
            "run": "X",
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
            (TOPIC_RECEIVE_FROM_DEVICES, 0),
            (TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
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
        topics = [(TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)]
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

    def start_batch_federated_learning(self, batch_config_path, expected_clients=None):
        """Start batch federated learning process from JSON configuration file"""
        self.logger.info("Starting Batch Federated Learning")
        
        # Load batch configuration
        try:
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
        
        self.logger.info(f"Batch folder: {batch_base_path}")
        
        # Setup MQTT subscriptions
        topics = [
            (TOPIC_RECEIVE_FROM_DEVICES, 0),
            (TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
        self.client.subscribe(topics)
        self.client.loop_start()
        
        self.logger.info(f"Starting batch processing of {len(batch_config)} configurations")
        
        # Process each test configuration sequentially
        successful_tests = 0
        failed_tests = 0
        
        for test_index, test_config in enumerate(batch_config):
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
        
        return True
    
    def _run_single_batch_test(self, test_config, test_number, expected_clients, batch_base_path=None):
        """Run a single federated learning test from batch configuration"""
        
        try:
            # Initialize federated learning state for this test
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            test_name = test_config.get('name', f'batch_test_{test_number}')
            
            # Use batch_base_path if provided (for batch mode), otherwise use WEIGHTS_FOLDER (for single mode)
            if batch_base_path:
                self.state.federated_path = os.path.join(batch_base_path, f"{timestamp}_{test_name}")
            else:
                self.state.federated_path = os.path.join(WEIGHTS_FOLDER, f"{timestamp}_{test_name}")
            self.state.current_round = 0
            self.state.is_federated = True
            self.state.connected_clients.clear()
            
            # Extract configuration
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
            
            if len(self.state.connected_clients) < 1:
                self.logger.error(f"Test {test_number}: No clients connected")
                return False
            
            if expected_clients and len(self.state.connected_clients) < expected_clients:
                self.logger.error(f"Test {test_number}: {len(self.state.connected_clients)}/{expected_clients} clients (insufficient)")
                self._send_unsubscribe_command()
                return False
            
            self.logger.info(f"Test {test_number} started with {len(self.state.connected_clients)} clients")
            
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
            
            self.state.max_rounds = max_rounds
            
            # Initialize federated clients tracking (progress != 'Completed' means waiting)
            self.state.federated_clients = {
                client_id: {'round': 1, 'progress': 'Training', 'last_update': time.time()}
                for client_id in self.state.connected_clients
            }
            
            self._send_command(json.dumps(start_command, separators=(',', ':')))
            
            # Save configuration with batch test info
            self._save_federated_config(start_command, test_config, test_number)
            
            # Run federated learning loop for this test
            success = self._run_single_test_loop()
            
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
            # Ensure cleanup happens even if test fails
            try:
                self._send_unsubscribe_command()
                sleep(2)  # Give time for cleanup
            except:
                pass  # Ignore cleanup errors
    
    def _run_single_test_loop(self):
        """Run federated learning loop for a single batch test"""
        status_timer = 0
        
        while True:
            sleep(1)
            status_timer += 1
            
            # Check if stop was requested
            if self.state.stop_requested:
                break
            
            # Check if all clients have submitted their models
            if len(self.state.waiting_for_clients) == 0:
                if self.state.current_round + 1 > self.state.max_rounds:
                    self.logger.info(f"Round {self.state.current_round}/{self.state.max_rounds} complete - last round!")
                    self.aggregate_weights(self.state.current_round)
                    break
                
                self.logger.info(f"Round {self.state.current_round}/{self.state.max_rounds} complete - all models received")
                sleep(1)
                
                # Aggregate weights and send to clients
                result = self.aggregate_weights(self.state.current_round)
                if result is None:
                    self.logger.error("Failed to aggregate weights for this test.")
                    return False
                
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
                
                self._send_binary_file(aggregated_binary_path)
                sleep(1)
                
                # Prepare for next round
                self.state.current_round += 1
                next_round_dir = os.path.join(self.state.federated_path, str(self.state.current_round))
                os.makedirs(next_round_dir, exist_ok=True)
                
                # Reset all federated clients for new round
                for client_id in self.state.federated_clients:
                    self.state.federated_clients[client_id]['round'] = self.state.current_round
                    self.state.federated_clients[client_id]['progress'] = 'Training'
                    self.state.federated_clients[client_id]['last_update'] = time.time()
                
                self.logger.debug(f"Weights sent. Starting round {self.state.current_round}")
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
            self.logger.info(f"Stop requested - ending round {self.state.current_round}/{self.state.max_rounds}")
            self.logger.debug("Sending unsubscribe command to devices")
            self._send_unsubscribe_command()
            sleep(2)  # Give time for devices to receive and process
            return False
        
        return True
    
    def _finalize_single_batch_test(self):
        """Finalize a single batch test"""
        # Create final round directory
        self.state.current_round += 1
        final_round_dir = os.path.join(self.state.federated_path, str(self.state.current_round))
        os.makedirs(final_round_dir, exist_ok=True)
        
        # Send end command
        end_command = {"command": "federate_end"}
        self._send_command(json.dumps(end_command, separators=(',', ':')))
        sleep(2)  # Shorter wait between batch tests
        
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
        print("For interactive mode, use the TUI: python server_tui.py")
                
    except KeyboardInterrupt:
        print("\nExiting")


if __name__ == "__main__":
    main()