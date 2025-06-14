import json
import paho.mqtt.client as mqtt
from datetime import datetime
from time import sleep
import os
import uuid
import traceback
import math
import struct
import numpy as np
from parser import do_parse

# Global configuration constants
BROKER_IP = "127.0.0.1"
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

# Directory paths
PARSE_FOLDER = "parse/"
WEIGHTS_FOLDER = "weights/"
METRICS_FOLDER = "metrics/"

# Federated learning configuration
DEFAULT_LAYERS = [3, 9, 6]
DEFAULT_ACTIVATION_FUNCTIONS = [1, 6]
DEFAULT_EPOCHS = 1
DEFAULT_LEARNING_RATE_WEIGHTS = 0.3333 / 12.0
DEFAULT_LEARNING_RATE_BIASES = 0.0666 / 12.0
DEFAULT_RANDOM_SEED = 10

# Timing constants
CONNECTION_WAIT_TIME = 10
COMMAND_RETRY_INTERVAL = 3
COMMAND_RETRIES = 3
STATUS_UPDATE_INTERVAL = 20


class FederatedServerState:
    """Class to manage federated server state"""
    
    def __init__(self):
        self.is_federated = False
        self.federated_path = ""
        self.current_round = 0
        self.max_rounds = 0
        self.connected_clients = []
        self.waiting_for_clients = []
        self.alive_clients = []
    
    def reset(self):
        """Reset server state"""
        self.is_federated = False
        self.federated_path = ""
        self.current_round = 0
        self.max_rounds = 0
        self.connected_clients.clear()
        self.waiting_for_clients.clear()
        self.alive_clients.clear()


class MQTTFederatedServer:
    """Main federated learning server class"""
    
    def __init__(self):
        self.client = mqtt.Client(client_id=f"Notebook-{uuid.uuid4()}", clean_session=True)
        self.state = FederatedServerState()
        self._setup_mqtt_client()
        
    def _setup_mqtt_client(self):
        """Configure MQTT client"""
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(BROKER_IP, BROKER_PORT, BROKER_KEEPALIVE)
        
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc != 0:
            print(f"Falha na conexão MQTT. Código de erro: {rc}")
            
    def _on_message(self, client, userdata, message):
        """MQTT message callback"""
        try:
            topic = message.topic
            topic_parts = topic.split('/')
            print(f"Mensagem recebida no tópico: {topic}")
            
            if topic_parts[2] == "model" and topic_parts[3] == "rawpush":
                print('Recebendo arquivo de rede neural...')
                self._handle_raw_push_message(topic_parts, message.payload)
            elif topic_parts[2] == "model" and topic_parts[3] == "push":
                self._handle_model_message(message.payload.decode("utf-8"))
            elif topic_parts[2] == "commands":
                self._handle_command_message(message.payload.decode("utf-8"))
                
        except UnicodeDecodeError as e:
            print(f"Erro ao decodificar mensagem: {e}")
            print(f"Payload: {message.payload}")
        except json.JSONDecodeError as e:
            print(f"Erro ao decodificar JSON: {e}")
            print(f"Payload: {message.payload}")
        except Exception as e:
            print(f"Erro inesperado ao processar mensagem: {e}")
            print(traceback.format_exc(e))
    
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
        
        # Remove client from waiting list if applicable
        if client_name in self.state.waiting_for_clients:
            self.state.waiting_for_clients.remove(client_name)
            
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
                print("Comando não especificado na mensagem")
                return
                
            if self.state.is_federated:
                self._handle_federated_command(command, client_id, command_data)
            elif command == "alive":
                self._handle_alive_command(client_id)
            else:
                print(payload)
                print("Comando não reconhecido ou federated learning não está ativo")
                
        except json.JSONDecodeError as e:
            print(f"Erro ao processar comando: {e}")
    
    def _handle_federated_command(self, command, client_id, command_data):
        """Handle federated learning specific commands"""
        if command == "join":
            self._handle_join_command(client_id)
        elif command == "leave":
            self._handle_leave_command(client_id)
        elif command == "resume":
            self._handle_resume_command(client_id)
        elif command == "alive":
            self._handle_federated_alive_command(client_id)
    
    def _handle_join_command(self, client_id):
        """Handle client join requests"""
        if client_id not in self.state.connected_clients:
            self.state.connected_clients.append(client_id)
            print(f"Cliente {client_id} se juntou ao servidor. "
                  f"Total de clientes: {len(self.state.connected_clients)}")
    
    def _handle_leave_command(self, client_id):
        """Handle client leave notifications"""
        if client_id in self.state.connected_clients:
            self.state.connected_clients.remove(client_id)
            print(f"Cliente {client_id} saiu do servidor.")
    
    def _handle_resume_command(self, client_id):
        """Handle client resume notifications"""
        if client_id in self.state.connected_clients:
            print(f"Cliente {client_id} está pronto para continuar.")
            try:
                resume_command = {
                    "command": "federate_resume",
                    "client": client_id,
                    "round": self.state.current_round
                }
                self._send_command(json.dumps(resume_command, separators=(',', ':')))
                
                aggregated_weights_path = os.path.join(
                    self.state.federated_path,
                    str(self.state.current_round - 1),
                    "aggregated_weights.json"
                )
                self._send_file(aggregated_weights_path, TOPIC_RESUME_TO_DEVICES)
                
            except Exception as e:
                print(f"Erro ao enviar arquivo de pesos: {e}")
    
    def _handle_federated_alive_command(self, client_id):
        """Handle alive messages in federated mode"""
        if client_id in self.state.connected_clients:
            print(f"Cliente {client_id} está ativo.")
    
    def _handle_alive_command(self, client_id):
        """Handle alive messages in normal mode"""
        if client_id not in self.state.alive_clients:
            self.state.alive_clients.append(client_id)
            self.state.alive_clients.sort()
        print(f"Total de clientes ativos: {len(self.state.alive_clients)} "
              f"{self.state.alive_clients}")
    
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

            # Check if neural network file exists and update waiting list
            nn_filepath = filepath.replace(".json", ".nn")
            if os.path.exists(nn_filepath) and client_name in self.state.waiting_for_clients:
                self.state.waiting_for_clients.remove(client_name)
            
            try:
                with open(filepath, 'x') as json_file:
                    json.dump(output_data, json_file, indent=4, separators=(',', ':'))
                print(f"Arquivo JSON salvo como: {filepath}")
            except FileExistsError:
                print(f"Arquivo JSON já existe: {filepath} Ignorando...")
                # File already exists, probably received twice - ignore
                pass
                
        except json.JSONDecodeError as e:
            print(f"Erro ao decodificar JSON: {e}")
            print(f"Dados recebidos: {data}")
    
    def _send_command(self, command_data, topic=TOPIC_SEND_COMMANDS_TO_DEVICES):
        """Send command via MQTT"""
        try:
            print("Enviando comando via MQTT...")
            self.client.publish(topic, command_data)
        except Exception as e:
            print(f"Erro ao enviar comando via MQTT: {e}")
    
    def _send_file(self, filepath, topic=TOPIC_SEND_TO_DEVICES):
        """Send file content via MQTT"""
        try:
            if os.path.exists(filepath):
                with open(filepath, "r") as file:
                    content = file.read().strip()
                    print(f"Enviando arquivo {filepath} via MQTT...")
                    self.client.publish(topic, content)
            else:
                print(f"Arquivo {filepath} não encontrado.")
        except Exception as e:
            print(f"Erro ao enviar arquivo via MQTT: {e}")
    
    def _read_binary_nn_file(self, filepath):
        """Read neural network from binary .nn file using the correct format"""
        try:
            with open(filepath, 'rb') as file:
                # Read number of layers
                layers_data = file.read(4)
                if len(layers_data) < 4:
                    return None
                numberOflayers = struct.unpack('<I', layers_data)[0]
                
                layers = []
                
                for i in range(numberOflayers):
                    layer_info = {}
                    
                    # Read activation function for this layer
                    actfunc_data = file.read(1)
                    if len(actfunc_data) < 1:
                        return None
                    activation_function = struct.unpack('<B', actfunc_data)[0]
                    
                    # Read layer inputs and outputs
                    inputs_data = file.read(4)
                    outputs_data = file.read(4)
                    if len(inputs_data) < 4 or len(outputs_data) < 4:
                        return None
                    
                    num_inputs = struct.unpack('<I', inputs_data)[0]
                    num_outputs = struct.unpack('<I', outputs_data)[0]
                    
                    layer_info['inputs'] = num_inputs
                    layer_info['outputs'] = num_outputs
                    layer_info['activation_function'] = activation_function
                    
                    # Read weights and biases for each output neuron
                    biases = []
                    weights = []
                    
                    for j in range(num_outputs):
                        # Read bias for this output neuron
                        bias_data = file.read(4)
                        if len(bias_data) < 4:
                            return None
                        bias_value = struct.unpack('<f', bias_data)[0]
                        biases.append(bias_value)
                        
                        # Read weights for this output neuron
                        neuron_weights = []
                        for k in range(num_inputs):
                            weight_data = file.read(4)
                            if len(weight_data) < 4:
                                return None
                            weight_value = struct.unpack('<f', weight_data)[0]
                            neuron_weights.append(weight_value)
                        
                        weights.append(neuron_weights)
                    
                    # Store layer information
                    layer_info['biases'] = np.array(biases, dtype=np.float32)
                    layer_info['weights'] = np.array(weights, dtype=np.float32)  # Shape: [outputs, inputs]
                    
                    layers.append(layer_info)
                
                return {
                    'numberOflayers': numberOflayers,
                    'layers': layers
                }
                
        except Exception as e:
            print(f"Erro ao ler arquivo binário {filepath}: {e}")
            return None
    
    def _write_binary_nn_file(self, filepath, network_data):
        """Write neural network to binary .nn file using the correct format"""
        try:
            with open(filepath, 'wb') as file:
                # Write number of layers
                file.write(struct.pack('<I', network_data['numberOflayers']))
                
                for layer in network_data['layers']:
                    # Write activation function
                    file.write(struct.pack('<B', layer['activation_function']))
                    
                    # Write layer inputs and outputs
                    file.write(struct.pack('<I', layer['inputs']))
                    file.write(struct.pack('<I', layer['outputs']))
                    
                    # Write biases and weights for each output neuron
                    for j in range(layer['outputs']):
                        # Write bias for this output neuron
                        file.write(struct.pack('<f', float(layer['biases'][j])))
                        
                        # Write weights for this output neuron
                        for k in range(layer['inputs']):
                            file.write(struct.pack('<f', float(layer['weights'][j][k])))
            
            print(f"Arquivo binário salvo: {filepath}")
            return True
            
        except Exception as e:
            print(f"Erro ao escrever arquivo binário {filepath}: {e}")
            return False
    
    def _send_binary_file(self, filepath, topic=TOPIC_SEND_TO_DEVICES):
        """Send binary file content via MQTT"""
        try:
            if os.path.exists(filepath):
                with open(filepath, "rb") as file:
                    content = file.read()
                    print(f"Enviando arquivo binário {filepath} via MQTT ({len(content)} bytes)...")
                    self.client.publish(topic, content)
            else:
                print(f"Arquivo binário {filepath} não encontrado.")
        except Exception as e:
            print(f"Erro ao enviar arquivo binário via MQTT: {e}")

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
            print(f"Usando método binário: {len(nn_files)} arquivos .nn encontrados")
            self._aggregate_weights_binary(source_dir, nn_files, round_number)
        else:
            # FALLBACK METHOD: Use JSON files if no .nn files found
            print("Nenhum arquivo .nn encontrado, tentando método JSON fallback...")
            json_files = [f for f in files if f.endswith('.json') and f != "aggregated_weights.json"]
            
            if json_files:
                print(f"Usando método JSON fallback: {len(json_files)} arquivos JSON encontrados")
                self._aggregate_weights_json(source_dir, json_files, round_number)
            else:
                print("Nenhum arquivo .nn ou .json encontrado para agregação.")
                return

    def _aggregate_weights_binary(self, source_dir, nn_files, round_number):
        """Aggregate using binary .nn files (primary method)"""
        # Read binary neural network data
        networks = []
        for file in nn_files:
            filepath = os.path.join(source_dir, file)
            network_data = self._read_binary_nn_file(filepath)
            if network_data is not None:
                networks.append(network_data)
                print(f"Lido arquivo {file}: {network_data['numberOflayers']} camadas")
        
        if not networks:
            print("Nenhum dado válido para agregação binária.")
            return
        
        # Verify all networks have the same structure
        first_network = networks[0]
        for i, network in enumerate(networks[1:], 1):
            if network['numberOflayers'] != first_network['numberOflayers']:
                print(f"Erro: Número de camadas diferente no arquivo {nn_files[i]}")
                return
            
            for layer_idx in range(network['numberOflayers']):
                first_layer = first_network['layers'][layer_idx]
                curr_layer = network['layers'][layer_idx]
                
                if (first_layer['inputs'] != curr_layer['inputs'] or 
                    first_layer['outputs'] != curr_layer['outputs']):
                    print(f"Erro: Estrutura da camada {layer_idx} diferente no arquivo {nn_files[i]}")
                    return
        
        print(f"Agregando {len(networks)} redes neurais (método binário)...")
        
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
            print(f"Camada {layer_idx}: {aggregated_layer['inputs']} -> {aggregated_layer['outputs']}")
        
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
            print(f"Pesos agregados salvos em: {output_path}")
            print(f"Agregados {len(networks)} modelos válidos.")
            
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
            print(f"Versão JSON salva em: {json_output_path}")
        else:
            print("Falha ao salvar pesos agregados.")

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
            print("Nenhum dado válido para agregação JSON.")
            return
        
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
            print("Nenhum dado válido encontrado para agregação JSON.")
            return
        
        print(f"Agregando {valid_count} modelos válidos (método JSON fallback)...")
        
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
        
        print(f"Pesos agregados salvos em: {output_path}")
        print(f"Agregados {valid_count} modelos válidos de {len(json_data)} total (método JSON).")
    
    def start_federated_learning(self):
        """Start federated learning process"""
        print('\33]0;Servidor Federado\a', end='', flush=True)
        
        # Setup MQTT subscriptions
        topics = [
            (TOPIC_RECEIVE_FROM_DEVICES, 0),
            (TOPIC_RECEIVE_FROM_DEVICES_RAW, 0),
            (TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
        self.client.subscribe(topics)
        self.client.loop_start()
        
        # Initialize federated learning state
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.state.federated_path = os.path.join(WEIGHTS_FOLDER, timestamp)
        self.state.current_round = 0
        self.state.is_federated = True
        self.state.connected_clients.clear()
        
        # Get configuration from user
        try:
            self.state.max_rounds = int(input("\nDigite o número de rodadas para o processo federativo: "))
            expected_clients = int(input("Digite o número de clientes esperados: "))
        except ValueError:
            print("Entrada inválida. Encerrando...")
            return
        
        # Create directories
        os.makedirs(self.state.federated_path, exist_ok=True)
        os.makedirs(os.path.join(self.state.federated_path, str(self.state.current_round)), exist_ok=True)
        
        # Wait for client connections
        print(f"Aguardando {CONNECTION_WAIT_TIME} segundos para conexão dos dispositivos...")
        
        for i in range(COMMAND_RETRIES):
            join_command = {"command": "federate_join"}
            self._send_command(json.dumps(join_command, separators=(',', ':')))
            sleep(COMMAND_RETRY_INTERVAL)
        
        if len(self.state.connected_clients) < 1:
            print("Nenhum cliente conectado. Encerrando...")
            self._cleanup_federated_learning()
            return
        
        if len(self.state.connected_clients) < expected_clients:
            print("Número insuficiente de clientes conectados. Encerrando...")
            self._send_unsubscribe_command()
            self._cleanup_federated_learning()
            return
        
        print(f"Federated learning iniciado com {len(self.state.connected_clients)} clientes.")
        
        # Create start command with neural network configuration
        start_command = {
            "command": "federate_start",
            "config": {
                "layers": DEFAULT_LAYERS,
                "actvFunctions": DEFAULT_ACTIVATION_FUNCTIONS,
                "epochs": DEFAULT_EPOCHS,
                "learningRateOfWeights": DEFAULT_LEARNING_RATE_WEIGHTS,
                "learningRateOfBiases": DEFAULT_LEARNING_RATE_BIASES,
                "randomSeed": DEFAULT_RANDOM_SEED
            }
        }
        
        # Initialize waiting list
        self.state.waiting_for_clients = self.state.connected_clients.copy()
        
        print(f"Configuração do processo federativo: {start_command['config']}")
        self._send_command(json.dumps(start_command, separators=(',', ':')))
        
        # Save configuration
        self._save_federated_config(start_command)
        
        # Main federated learning loop
        self._run_federated_learning_loop()
        
        # Cleanup
        self._finalize_federated_learning()
    
    def _save_federated_config(self, start_command):
        """Save federated learning configuration"""
        config = start_command["config"].copy()
        config["devices"] = sorted(self.state.connected_clients)
        
        # Calculate neural network parameters
        layers = config["layers"]
        total_neurons = sum(layers[i] * layers[i+1] for i in range(len(layers) - 1))
        
        config.update({
            "neurons": total_neurons,
            "device_count": len(self.state.connected_clients),
            "bits": "32",
            "run": "X"
        })
        
        config_path = os.path.join(self.state.federated_path, "config.json")
        with open(config_path, 'w') as f:
            json.dump(start_command, f, indent=4, separators=(',', ':'))
    
    def _run_federated_learning_loop(self):
        """Main federated learning training loop"""
        status_timer = 0
        
        while True:
            sleep(1)
            status_timer += 1
            
            # Check if all clients have submitted their models
            if len(self.state.waiting_for_clients) == 0:
                if self.state.current_round + 1 >= self.state.max_rounds:
                    print("Número máximo de rodadas atingido.")
                    self.aggregate_weights(self.state.current_round)
                    break
                
                print("Todos os arquivos recebidos para esta rodada.")
                sleep(1)
                
                # Aggregate weights and send to clients
                self.aggregate_weights(self.state.current_round)
                
                # Send binary aggregated weights to devices
                aggregated_binary_path = os.path.join(
                    self.state.federated_path,
                    str(self.state.current_round),
                    "aggregated_weights.nn"
                )
                self._send_binary_file(aggregated_binary_path)
                sleep(1)
                
                # Prepare for next round
                self.state.current_round += 1
                next_round_dir = os.path.join(self.state.federated_path, str(self.state.current_round))
                os.makedirs(next_round_dir, exist_ok=True)
                
                self.state.waiting_for_clients = self.state.connected_clients.copy()
                print(f"Pesos enviados. Iniciando próximo round: {self.state.current_round}")
                status_timer = 0
                
            elif status_timer >= STATUS_UPDATE_INTERVAL:
                received_count = len(self.state.connected_clients) - len(self.state.waiting_for_clients)
                total_count = len(self.state.connected_clients)
                
                print(f"Arquivos recebidos: {received_count} de {total_count}. "
                      f"Aguardando: {self.state.waiting_for_clients}")
                status_timer = 0
    
    def _finalize_federated_learning(self):
        """Finalize federated learning process"""
        # Create final round directory
        self.state.current_round += 1
        final_round_dir = os.path.join(self.state.federated_path, str(self.state.current_round))
        os.makedirs(final_round_dir, exist_ok=True)
        
        # Send end command
        end_command = {"command": "federate_end"}
        self._send_command(json.dumps(end_command, separators=(',', ':')))
        sleep(5)
        
        # Send unsubscribe command
        self._send_unsubscribe_command()
        
        # Mark completion
        done_path = os.path.join(self.state.federated_path, "done.json")
        with open(done_path, 'w') as f:
            json.dump({}, f, indent=4, separators=(',', ':'))
        
        self._cleanup_federated_learning()
    
    def _send_unsubscribe_command(self):
        """Send unsubscribe command to all clients"""
        unsubscribe_command = {"command": "federate_unsubscribe"}
        self._send_command(json.dumps(unsubscribe_command, separators=(',', ':')))
    
    def _cleanup_federated_learning(self):
        """Clean up federated learning state"""
        self.state.reset()
    
    def start_listening_mode(self):
        """Start listening mode - just receive and save messages"""
        print('\33]0;Listen - Servidor Federado\a', end='', flush=True)
        
        topics = [
            (TOPIC_RECEIVE_FROM_DEVICES, 0),
            (TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)
        ]
        self.client.subscribe(topics)
        
        print("Escutando mensagens MQTT... Pressione Ctrl+C para sair.")
        self.client.loop_forever()
    
    def request_models_from_devices(self):
        """Request models from all connected devices"""
        request_command = {"command": "request_model"}
        self._send_command(json.dumps(request_command, separators=(',', ':')))
        print("Solicitação de modelos enviada para os dispositivos.")
    
    def check_alive_devices(self):
        """Check which devices are alive"""
        topics = [(TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)]
        self.client.subscribe(topics)
        
        self.state.alive_clients.clear()
        
        print("Enviando sinal de vida para os dispositivos...")
        alive_command = {"command": "federate_alive"}
        
        self._send_command(json.dumps(alive_command, separators=(',', ':')))
        # for _ in range(COMMAND_RETRIES):
        #     sleep(2)
        
        self.client.loop_forever()
    
    def send_aggregated_weights(self):
        """Aggregate weights and send to devices"""
        self.aggregate_weights()
        # Send binary aggregated weights instead of JSON
        aggregated_binary_path = os.path.join(WEIGHTS_FOLDER, "aggregated_weights.nn")
        self._send_binary_file(aggregated_binary_path)
    
    def parse_training_data(self):
        """Parse training data and generate visualizations"""
        do_parse(PARSE_FOLDER, METRICS_FOLDER)
    
    def disconnect(self):
        """Disconnect MQTT client"""
        self.client.disconnect()
        print("Cliente MQTT desconectado.")


def print_menu():
    """Print user menu options"""
    menu_options = [
        "'send' \tpara agregar os modelos disponíveis e enviar aos dispositivos",
        "'request' \tpara solicitar modelos dos dispositivos",
        "'listen' \tpara montar um servidor que apenas escuta mensagens e salva",
        "'federate' \tpara abrir um servidor federado",
        "'parse' \tpara processar os dados e gerar visualizações",
        "'alive' \tpara verificar dispositivos ativos",
        "'unsub' \tpara forçar encerramento do processo federativo nos clientes"
    ]
    
    print("\nOpções disponíveis:")
    for option in menu_options:
        print(f" {option}")
    
    return input("\nEscreva a opção desejada: ").strip().lower()


def main():
    """Main application entry point"""
    print('\33]0;Escolha comando\a', end='', flush=True)
    
    # Initialize server
    server = MQTTFederatedServer()
    
    try:
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
                
            elif user_input == 'parse':
                server.parse_training_data()
                
            elif user_input == 'unsub':
                server._send_unsubscribe_command()
                
            elif user_input == 'alive':
                server.check_alive_devices()
                
            else:
                print("Comando inválido. Tente novamente.")
                
    except KeyboardInterrupt:
        print("\nSaindo...")
    finally:
        server.disconnect()


if __name__ == "__main__":
    main()