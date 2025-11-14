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
        
        # Convenience methods for different log levels
        self._log_debug = self.logger.debug
        self._log_info = self.logger.info
        self._log_warning = self.logger.warning
        self._log_error = self.logger.error
        self._log_critical = self.logger.critical
        
        # Keep _log as alias to info for backward compatibility
        self._log = self.logger.info
        
    def _setup_mqtt_client(self):
        """Configure MQTT client"""
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(BROKER_IP, BROKER_PORT, BROKER_KEEPALIVE)
        
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc != 0:
            self._log(f"Falha na conexão MQTT. Código de erro: {rc}")
            
    def _on_message(self, client, userdata, message):
        """MQTT message callback"""
        try:
            topic = message.topic
            topic_parts = topic.split('/')
            if self.debug:
                self._log(f"Mensagem recebida no tópico: {topic}")
            
            if topic_parts[2] == "model" and topic_parts[3] == "rawpush":
                if self.debug:
                    self._log('Recebendo arquivo de rede neural...')
                self._handle_raw_push_message(topic_parts, message.payload)
            elif topic_parts[2] == "model" and topic_parts[3] == "push":
                if self.debug:
                    self._log('Recebendo mensagem de modelo...')
                self._handle_model_message(message.payload.decode("utf-8"))
            elif topic_parts[2] == "commands":
                self._handle_command_message(message.payload.decode("utf-8"))
                
        except UnicodeDecodeError as e:
            self._log(f"Erro ao decodificar mensagem: {e}")
            self._log(f"Payload: {message.payload}")
        except json.JSONDecodeError as e:
            self._log(f"Erro ao decodificar JSON: {e}")
            self._log(f"Payload: {message.payload}")
        except Exception as e:
            self._log(f"Erro inesperado ao processar mensagem: {e}")
            self._log(traceback.format_exc())
    
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
                self._log("⚠️ Comando não especificado na mensagem")
                return
                
            if self.state.is_federated:
                self._handle_federated_command(command, client_id, command_data)
            elif command == "alive":
                self._handle_alive_command(client_id)
            else:
                self._log(f"⚠️ Comando não reconhecido: {payload}")
                
        except json.JSONDecodeError as e:
            self._log(f"❌ Erro ao processar comando: {e}")
    
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
            self._log(f"Cliente {client_id} se juntou ao servidor. "
                      f"Total de clientes: {len(self.state.connected_clients)}")
    
    def _handle_leave_command(self, client_id):
        """Handle client leave notifications"""
        if client_id in self.state.connected_clients:
            del self.state.connected_clients[client_id]
            self._log(f"Cliente {client_id} saiu do servidor.")
    
    def _handle_resume_command(self, client_id):
        """Handle client resume notifications"""
        if client_id in self.state.connected_clients:
            self._log(f"Cliente {client_id} está pronto para continuar.")
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
                    self._log(f"Enviando arquivo binário de retomada para {client_id}")
                    self._send_binary_file(aggregated_binary_path, f"{TOPIC_RESUME_TO_DEVICES_RAW}/{client_id}")
                else:
                    # Fallback to JSON if binary file doesn't exist
                    aggregated_json_path = os.path.join(
                        self.state.federated_path,
                        str(self.state.current_round - 1),
                        "aggregated_weights.json"
                    )
                    self._log(f"⚠️ Arquivo binário não encontrado, enviando JSON para {client_id}")
                    self._send_file(aggregated_json_path, TOPIC_RESUME_TO_DEVICES)
                
            except Exception as e:
                self._log(f"❌ Erro ao enviar arquivo de pesos: {e}")
    
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
                self._log(f"⚠️ Arquivo JSON já existe: {filepath} Ignorando...")
                # File already exists, probably received twice - ignore
                pass
                
        except json.JSONDecodeError as e:
            self._log(f"❌ Erro ao decodificar JSON: {e}")
            self._log(f"Dados recebidos: {data}")
    
    def _send_command(self, command_data, topic=TOPIC_SEND_COMMANDS_TO_DEVICES):
        """Send command via MQTT"""
        try:
            if self.debug:
                self._log("📤 Enviando comando via MQTT...")
            self.client.publish(topic, command_data)
        except Exception as e:
            self._log(f"❌ Erro ao enviar comando via MQTT: {e}")
    
    def _send_file(self, filepath, topic=TOPIC_SEND_TO_DEVICES):
        """Send file content via MQTT"""
        try:
            if os.path.exists(filepath):
                with open(filepath, "r") as file:
                    content = file.read().strip()
                    self.client.publish(topic, content)
            else:
                self._log(f"❌ Arquivo {filepath} não encontrado")
        except Exception as e:
            self._log(f"❌ Erro ao enviar arquivo via MQTT: {e}")
    
    def _read_binary_nn_file(self, filepath):
        """Lê arquivo binário .nn com formato ESP32"""
        try:
            # Use the reader with activation function support
            network = read_nn_binary_with_activation(filepath)
            
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
                self._log(f"❌ Falha ao carregar rede neural de {filepath}")
                return None
            
        except Exception as e:
            self._log(f"❌ Erro ao ler arquivo {filepath}: {e}")
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
            self._log(f"❌ Erro ao escrever arquivo binário {filepath}: {e}")
            return False
    
    def _send_binary_file(self, filepath, topic=TOPIC_SEND_TO_DEVICES_RAW):
        """Send binary file content via MQTT"""
        try:
            if os.path.exists(filepath):
                with open(filepath, "rb") as file:
                    content = file.read()
                    self._log(f"📤 Enviando arquivo binário ({len(content)/1024:.1f} KB)")
                    self.client.publish(topic, content)
            else:
                self._log(f"❌ Arquivo binário {filepath} não encontrado")
        except Exception as e:
            self._log(f"❌ Erro ao enviar arquivo binário via MQTT: {e}")

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
        
        if nn_files:
            return self._aggregate_weights_binary(source_dir, nn_files, round_number)
        else:
            # FALLBACK METHOD: Use JSON files if no .nn files found
            self._log("⚠️ Nenhum arquivo .nn encontrado, tentando método JSON fallback...")
            json_files = [f for f in files if f.endswith('.json') and f != "aggregated_weights.json"]
            
            if json_files:
                self._log(f"📊 Usando método JSON fallback: {len(json_files)} arquivos JSON encontrados")
                return self._aggregate_weights_json(source_dir, json_files, round_number)
            else:
                self._log("❌ Nenhum arquivo .nn ou .json encontrado para agregação")
                return None

    def _aggregate_weights_binary(self, source_dir, nn_files, round_number):
        """Aggregate using binary .nn files (primary method)"""
        self._log(f"🔄 Agregando {len(nn_files)} modelos binários (rodada {round_number})...")
        
        # Read binary neural network data
        networks = []
        for file in nn_files:
            filepath = os.path.join(source_dir, file)
            network_data = self._read_binary_nn_file(filepath)
            if network_data is not None:
                networks.append(network_data)
                 
        if not networks:
            self._log("❌ Nenhum dado válido para agregação binária.")
            return None

        # Verify all networks have the same structure
        first_network = networks[0]
        for i, network in enumerate(networks[1:], 1):
            if network['numberOflayers'] != first_network['numberOflayers']:
                self._log(f"❌ Erro: Número de camadas diferente no arquivo {nn_files[i]}")
                return None
            
            for layer_idx in range(network['numberOflayers']):
                first_layer = first_network['layers'][layer_idx]
                curr_layer = network['layers'][layer_idx]
                
                if (first_layer['inputs'] != curr_layer['inputs'] or
                    first_layer['outputs'] != curr_layer['outputs']):
                    self._log(f"❌ Erro: Estrutura de camada diferente no arquivo {nn_files[i]}")
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
                self._log(f"   Camada {layer_idx}: {aggregated_layer['inputs']} → {aggregated_layer['outputs']}")
        
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
            self._log(f"✅ Agregados {len(networks)} modelos válidos")
            
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
            self._log("❌ Falha ao salvar pesos agregados")
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
            self._log("❌ Nenhum dado válido para agregação JSON")
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
            self._log("❌ Nenhum dado válido encontrado para agregação JSON")
            return None
        
        self._log(f"🔄 Agregando {valid_count} modelos válidos (método JSON fallback)...")
        
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
        
        self._log(f"💾 Pesos agregados salvos em: {output_path}")
        self._log(f"✅ Agregados {valid_count} modelos válidos de {len(json_data)} total (método JSON)")
        return output_path
    
    def start_federated_learning(self, max_rounds=None, expected_clients=None):
        """Start federated learning process"""
        self._log("🚀 Iniciando Federated Learning...")
        
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
                max_rounds = int(input("\nDigite o número de rodadas para o processo federativo: "))
            
            if expected_clients is not None:
                expected_clients = expected_clients
            else:
                expected_clients = int(input("Digite o número de clientes esperados: "))
        except ValueError:
            self._log("Entrada inválida. Encerrando...")
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
        
        self._log(f"Configuração: {max_rounds} rodadas, {expected_clients} clientes esperados")
        
        # Run single federated learning session using shared code
        success = self._run_single_batch_test(test_config, 1, expected_clients, None)
        
        if success:
            # Use the shared finalization
            self._finalize_single_batch_test()
            self._log("✅ Federated learning concluído com sucesso.")
        else:
            self._log("❌ Federated learning falhou.")
        
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
            self._log("❌ Federated learning não está ativo")
            return False
        
        if self.state.is_paused:
            self._log("⚠️  Federated learning já está pausado")
            return False
        
        self.state.is_paused = True
        self._log("⏸️  Federated learning pausado")
        return True
    
    def resume_federated_learning(self):
        """Resume federated learning - send accumulated weights"""
        if not self.state.is_federated:
            self._log("❌ Federated learning não está ativo")
            return False
        
        if not self.state.is_paused:
            self._log("⚠️  Federated learning não está pausado")
            return False
        
        self.state.is_paused = False
        self._log("▶️  Federated learning retomado")
        return True
    
    def start_listening_mode(self):
        """Start listening mode - just receive and save messages"""
        self._log("👂 Iniciando modo de escuta...")
        self.client.loop_stop()
        
        topics = [
            (TOPIC_RECEIVE_FROM_DEVICES, 0),
            (TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
        self.client.subscribe(topics)
        
        self._log("📡 Escutando mensagens MQTT... Pressione Ctrl+C para sair")
        self.client.loop_forever()
    
    def request_models_from_devices(self):
        """Request models from all connected devices"""
        request_command = {"command": "request_model"}
        self._send_command(json.dumps(request_command, separators=(',', ':')))
        self._log("📨 Solicitação de modelos enviada para os dispositivos")
    
    def check_alive_devices(self):
        """Check which devices are alive"""
        self.client.loop_stop()
        topics = [(TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)]
        self.client.subscribe(topics)
        
        self._log("💓 Enviando sinal de vida para os dispositivos...")
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
                    self._log(f"📂 Processando pasta: {folder}")
                    do_parse(folder, metrics)
    
    def disconnect(self):
        """Disconnect MQTT client"""
        self.client.disconnect()
        self._log("🔌 Cliente MQTT desconectado")

    def start_batch_federated_learning(self, batch_config_path, expected_clients=None):
        """Start batch federated learning process from JSON configuration file"""
        self._log("🚀 Iniciando Batch Federated Learning...")
        
        # Load batch configuration
        try:
            with open(batch_config_path, 'r') as f:
                batch_config = json.load(f)
        except FileNotFoundError:
            self._log(f"❌ Arquivo de configuração não encontrado: {batch_config_path}")
            return
        except json.JSONDecodeError as e:
            self._log(f"❌ Erro ao decodificar JSON: {e}")
            return
        
        if not isinstance(batch_config, list):
            self._log("❌ Configuração deve ser uma lista de objetos de teste")
            return
        
        # Create batch-specific folder
        batch_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        batch_folder_name = f"batch_{batch_timestamp}"
        batch_base_path = os.path.join(WEIGHTS_FOLDER, batch_folder_name)
        os.makedirs(batch_base_path, exist_ok=True)
        
        self._log(f"📁 Pasta do lote: {batch_base_path}")
        
        # Setup MQTT subscriptions
        topics = [
            (TOPIC_RECEIVE_FROM_DEVICES, 0),
            (TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
        self.client.subscribe(topics)
        self.client.loop_start()
        
        self._log(f"🚀 Iniciando processamento em lote de {len(batch_config)} configurações...")
        
        # Process each test configuration sequentially
        successful_tests = 0
        failed_tests = 0
        
        for test_index, test_config in enumerate(batch_config):
            self._log(f"\n{'='*60}")
            self._log(f"INICIANDO TESTE {test_index + 1} de {len(batch_config)}")
            self._log(f"{'='*60}")
            
            # Validate test configuration
            if not self._validate_test_config(test_config, test_index + 1):
                self._log(f"❌ Teste {test_index + 1} falhou na validação. Continuando para o próximo teste.")
                failed_tests += 1
                continue
            
            # Run single federated learning session
            success = self._run_single_batch_test(test_config, test_index + 1, expected_clients, batch_base_path)
            
            if not success:
                self._log(f"❌ Teste {test_index + 1} falhou. Continuando para o próximo teste.")
                failed_tests += 1
            else:
                self._log(f"✅ Teste {test_index + 1} concluído com sucesso.")
                successful_tests += 1
            
            # Wait between tests if not the last one
            if test_index < len(batch_config) - 1:
                self._log(f"⏳ Aguardando 5 segundos antes do próximo teste...")
                sleep(5)
        
        self._log(f"\n{'='*60}")
        self._log("PROCESSAMENTO EM LOTE CONCLUÍDO")
        self._log(f"{'='*60}")
        self._log(f"📊 Resumo dos testes:")
        self._log(f"   ✅ Testes bem-sucedidos: {successful_tests}")
        self._log(f"   ❌ Testes falharam: {failed_tests}")
        self._log(f"   📁 Total de testes: {len(batch_config)}")
        self._log(f"   📁 Pasta do lote: {batch_base_path}")
        
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
            self._log(f"✅ Processamento em lote concluído com {successful_tests} teste(s) bem-sucedido(s).")
        else:
            self._log(f"❌ Nenhum teste foi bem-sucedido.")
        
        self._log(f"📄 Resumo salvo em: {summary_path}")
        
        # Final cleanup
        self._cleanup_federated_learning()
    
    def _validate_test_config(self, test_config, test_number):
        """Validate individual test configuration"""
        required_fields = ['epochs', 'layers', 'activationFunctions', 'learningRateWeights', 'learningRateBiases', 'seed']
        
        for field in required_fields:
            if field not in test_config:
                self._log(f"❌ Teste {test_number}: Campo obrigatório '{field}' não encontrado")
                return False
        
        # Validate layers and activation functions match
        layers = test_config['layers']
        activation_funcs = test_config['activationFunctions']
        
        if not isinstance(layers, list) or len(layers) < 2:
            self._log(f"❌ Teste {test_number}: 'layers' deve ser uma lista com pelo menos 2 elementos")
            return False
        
        if not isinstance(activation_funcs, list) or len(activation_funcs) != len(layers) - 1:
            self._log(f"❌ Teste {test_number}: 'activationFunctions' deve ter {len(layers) - 1} elementos")
            return False
        
        # Validate numeric values
        if not isinstance(test_config['epochs'], int) or test_config['epochs'] < 1:
            self._log(f"❌ Teste {test_number}: 'epochs' deve ser um inteiro positivo")
            return False
        
        if not isinstance(test_config['learningRateWeights'], (int, float)) or test_config['learningRateWeights'] <= 0:
            self._log(f"❌ Teste {test_number}: 'learningRateWeights' deve ser um número positivo")
            return False
        
        if not isinstance(test_config['learningRateBiases'], (int, float)) or test_config['learningRateBiases'] <= 0:
            self._log(f"❌ Teste {test_number}: 'learningRateBiases' deve ser um número positivo")
            return False
        
        if not isinstance(test_config['seed'], int):
            self._log(f"❌ Teste {test_number}: 'seed' deve ser um inteiro")
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
            
            self._log(f"⚙️ Configuração do teste {test_number}: {test_name}")
            self._log(f"   Épocas: {test_config['epochs']}, Rodadas: {max_rounds}")
            self._log(f"   Camadas: {test_config['layers']}")
            if self.debug:
                self._log(f"   Funções ativação: {test_config['activationFunctions']}")
                self._log(f"   LR pesos: {test_config['learningRateWeights']}, LR bias: {test_config['learningRateBiases']}")
                self._log(f"   Seed: {test_config['seed']}, JSON weights: {test_config.get('sendJsonWeights', False)}")
            
            # Create directories
            os.makedirs(self.state.federated_path, exist_ok=True)
            os.makedirs(os.path.join(self.state.federated_path, str(self.state.current_round)), exist_ok=True)
            
            # Wait for client connections
            self._log(f"⏳ Aguardando {CONNECTION_WAIT_TIME}s para conexão dos dispositivos...")

            for i in range(COMMAND_RETRIES):
                unsub_command = {"command": "federate_unsubscribe"}
                self._send_command(json.dumps(unsub_command, separators=(',', ':')))
                sleep(COMMAND_RETRY_INTERVAL)
            
            for i in range(COMMAND_RETRIES):
                join_command = {"command": "federate_join"}
                self._send_command(json.dumps(join_command, separators=(',', ':')))
                sleep(COMMAND_RETRY_INTERVAL)
            
            if len(self.state.connected_clients) < 1:
                self._log(f"❌ Teste {test_number}: Nenhum cliente conectado")
                return False
            
            if expected_clients and len(self.state.connected_clients) < expected_clients:
                self._log(f"❌ Teste {test_number}: {len(self.state.connected_clients)}/{expected_clients} clientes (insuficiente)")
                self._send_unsubscribe_command()
                return False
            
            self._log(f"✅ Teste {test_number} iniciado com {len(self.state.connected_clients)} clientes")
            
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
            self._log(f"❌ Erro inesperado no teste {test_number}: {e}")
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
            
            # Check if all clients have submitted their models
            if len(self.state.waiting_for_clients) == 0:
                if self.state.current_round + 1 > self.state.max_rounds:
                    self._log(f"✅ Rodada {self.state.current_round}/{self.state.max_rounds} completa - última rodada!")
                    self.aggregate_weights(self.state.current_round)
                    break
                
                self._log(f"✅ Rodada {self.state.current_round}/{self.state.max_rounds} completa - todos os modelos recebidos")
                sleep(1)
                
                # Aggregate weights and send to clients
                result = self.aggregate_weights(self.state.current_round)
                if result is None:
                    self._log("❌ Falha ao agregar pesos para este teste.")
                    return False
                
                # Send binary aggregated weights to devices (unless paused)
                aggregated_binary_path = os.path.join(
                    self.state.federated_path,
                    str(self.state.current_round),
                    "aggregated_weights.nn"
                )
                
                if self.state.is_paused:
                    self.state.paused_aggregated_path = aggregated_binary_path
                    self._log("⏸️  Treinamento pausado - pesos agregados mas não enviados")
                    # Wait until resumed
                    while self.state.is_paused:
                        sleep(0.5)
                    self._log("▶️  Treinamento retomado - enviando pesos agregados")
                
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
                
                self._log(f"📤 Pesos enviados. Iniciando rodada {self.state.current_round}")
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

                self._log(f"📊 Status: {received_count}/{total_count} recebidos | Aguardando: {waiting} | Ativos: {alive_count}")
                status_timer = 0
        
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


def print_menu():
    """Print user menu options"""
    menu_options = [
        "'send' \tpara agregar os modelos disponíveis e enviar aos dispositivos",
        "'request' \tpara solicitar modelos dos dispositivos",
        "'listen' \tpara montar um servidor que apenas escuta mensagens e salva",
        "'federate' \tpara abrir um servidor federado",
        "'batch' \tpara executar processamento em lote com configuração JSON",
        "'parse' \tpara processar os dados e gerar visualizações",
        "'parseall' \tpara processar todos os dados e gerar todas as visualizações",
        "'batchcompare' \tpara comparar métricas entre testes de batch",
        "'alive' \tpara verificar dispositivos ativos",
        "'unsub' \tpara forçar encerramento do processo federativo nos clientes"
    ]
    
    print("\nOpções disponíveis:")
    for option in menu_options:
        print(f" {option}")
    
    return input("\nEscreva a opção desejada: ").strip().lower()


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
                print("Executando comando 'alive'...")
                server.check_alive_devices()
                
            elif args.command == 'federate':
                print(f"Iniciando servidor federado com {args.rounds} rodadas e {args.clients} clientes esperados...")
                server.start_federated_learning(max_rounds=args.rounds, expected_clients=args.clients)
                
            elif args.command == 'batch':
                print(f"Iniciando processamento em lote usando configuração: {args.config}")
                if args.clients:
                    print(f"Esperando {args.clients} clientes...")
                server.start_batch_federated_learning(args.config, expected_clients=args.clients)
                
            elif args.command == 'parse':
                print("Processando dados de treinamento e gerando visualizações...")
                if args.folder:
                    print(f"Usando pasta especificada: {args.folder}")
                server.parse_training_data(args.folder)
                
            elif args.command == 'parseall':
                print("Processando todos os dados de treinamento e gerando todas as visualizações...")
                if args.folder:
                    print(f"Buscando dados na pasta: {args.folder}")
                server.parse_all_training_data(args.folder)
                
            elif args.command == 'batchcompare':
                print("Comparando métricas entre testes de batch...")
                batch_folder = args.batch_folder
                output_folder = args.output if args.output else None
                
                plot_batch_comparison(batch_folder, output_folder)
                if output_folder:
                    print(f"Comparação concluída! Gráficos salvos em: {output_folder}")
                else:
                    print(f"Comparação concluída! Gráficos salvos em: {os.path.join(batch_folder, 'metrics')}")
                
            elif args.command == 'unsub':
                print("Enviando comando de unsubscribe...")
                server._send_unsubscribe_command()
                sleep(2)  # Give time for the command to be sent
                
            return  # Exit after executing the command
        
        # If no command line arguments, use interactive menu
        print('\33]0;Escolha comando\a', end='', flush=True)

        # CLI mode - enable stdout logging
        server = MQTTFederatedServer(debug=False, enable_stdout=True)

        server.client.loop_start()

        while True:
            user_input = print_menu()
            
            if user_input == 'send':
                server.send_aggregated_weights()
                
            elif user_input == 'listen':
                server.start_listening_mode()
                
            elif user_input == 'request':
                server.request_models_from_devices()
                
            elif user_input == 'federate':
                server.start_federated_learning()
                
            elif user_input == 'batch':
                config_path = input("Digite o caminho para o arquivo de configuração JSON: ").strip()
                try:
                    clients_input = input("Digite o número de clientes esperados (opcional, pressione Enter para pular): ").strip()
                    expected_clients = int(clients_input) if clients_input else None
                except ValueError:
                    expected_clients = None
                server.start_batch_federated_learning(config_path, expected_clients)
                
            elif user_input == 'parse':
                folder = input("Digite o caminho da pasta para processar (ou pressione Enter para usar padrão): ").strip()
                folder = folder if folder else None
                server.parse_training_data(folder)
            
            elif user_input == 'parseall':
                folder = input("Digite o caminho da pasta base para buscar dados (ou pressione Enter para usar padrão): ").strip()
                folder = folder if folder else None
                server.parse_all_training_data(folder)
                
            elif user_input == 'batchcompare':
                batch_folder = input("Digite o caminho da pasta do batch: ").strip()
                output_folder = input("Digite o caminho de saída (ou pressione Enter para usar padrão batch_folder/metrics/): ").strip()
                
                if not output_folder:
                    output_folder = None
                
                print("Comparando métricas entre testes do batch...")
                plot_batch_comparison(batch_folder, output_folder)
                if output_folder:
                    print(f"Comparação concluída! Gráficos salvos em: {output_folder}")
                else:
                    print(f"Comparação concluída! Gráficos salvos em: {os.path.join(batch_folder, 'metrics')}")
                
            elif user_input == 'unsub':
                server._send_unsubscribe_command()
                
            elif user_input == 'alive':
                server.check_alive_devices()
                break
                
            else:
                print("Comando inválido. Tente novamente.")
                
    except KeyboardInterrupt:
        print("\nSaindo...")
    finally:
        server.disconnect()


if __name__ == "__main__":
    main()