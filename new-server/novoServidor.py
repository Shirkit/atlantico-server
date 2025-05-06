import json
import paho.mqtt.client as mqtt
from datetime import datetime
from pprint import pprint
from time import sleep
import os
import matplotlib.pyplot as plt
import re
from collections import defaultdict

# Variável para armazenar os dados recebidos
shared_state = {}

federate = False
federate_round = 0
federate_path = ""


BROKER_IP = "127.0.0.1"
TOPIC_RECEIVE_FROM_DEVICES = "esp32/fl/model/push"
TOPIC_RECEIVE_COMMANDS_FROM_DEVICES = "esp32/fl/commands/push"
TOPIC_SEND_TO_DEVICES = "esp32/fl/model/pull"
TOPIC_SEND_COMMANDS_TO_DEVICES = "esp32/fl/commands/pull"
PARSE_FOLDER = "parse/"
WEIGHTS_FOLDER = "pesos/"

federate_clients = []
# ready_clients = []

def dump(obj):
  for attr in dir(obj):
    print("obj.%s = %r" % (attr, getattr(obj, attr)))

def on_connect(client, userdata, flags, rc):
    if rc != 0:
        print(f"Falha na conexão. Código de erro: {rc}")

# Função chamada quando uma mensagem MQTT é recebida
def on_message(client, userdata, message):
    payload = message.payload.decode("utf-8")
    topic = message.topic

    topic_parts = message.topic.split('/')
    if (topic_parts[2] == "model"):
        # save_file(payload, client)
        save_to_json_file(payload)
    elif (topic_parts[2] == "commands"):
        parse_command(payload)

def parse_command(payload):
    msg = json.loads(payload)
    if "command" in msg:
        if msg["command"] == "join":
            if (msg["client"] not in federate_clients):
                federate_clients.append(msg["client"])
                print(f"Cliente {msg['client']} se juntou ao servidor.")
        elif msg["command"] == "leave":
            if (msg["client"] in federate_clients):
                federate_clients.remove(msg["client"])
                print(f"Cliente {msg['client']} saiu do servidor.")
        # elif msg["command"] == "ready":
        #     if (msg["client"] not in ready_clients) and (msg["client"] in federate_clients):
        #         ready_clients.append(msg["client"])
        #         print(f"Cliente {msg['client']} está pronto.")

def save_to_json_file(data):
    try:
        output_data = {
            "received_time": datetime.now().isoformat(),
            "data": json.loads(data),
        }
        clientname = output_data["data"]["client"]
        filepath = ""

        global shared_state

        if shared_state and shared_state.get("federate") is True:
            filepath = shared_state["federate_path"] + str(shared_state["federate_round"]) + "/" + clientname + ".json"
        else:
            filepath = WEIGHTS_FOLDER + clientname + ".json"
        with open(filepath, 'w') as json_file:
            json.dump(output_data, json_file, indent=4)
        print(f"Arquivo JSON salvo como {filepath}")

    except json.JSONDecodeError as e:
        print(f"Erro ao decodificar JSON: {e}")
        print(f"Dados recebidos: {data}")

def read_file(caminho_arquivo):
    try:
        if os.path.exists(caminho_arquivo):
            with open(caminho_arquivo, "r") as file:
                conteudo = file.read().strip()
                return conteudo
        else:
            print(f"Arquivo {caminho_arquivo} não encontrado.")
            return None
    except Exception as e:
        print(f"Erro ao ler o arquivo {caminho_arquivo}: {e}")
        return None

def send_mqtt(data = None, filepath = None):
    try:
        if filepath:
            new_weights = read_file(filepath)
            if new_weights:
                print("Enviando arquivo " + filepath + " via MQTT...")
                client.publish(TOPIC_SEND_TO_DEVICES, new_weights)
        if data:
            print("Enviando dados via MQTT...")
            client.publish(TOPIC_SEND_TO_DEVICES, data)
    except Exception as e:
        print(f"Erro ao enviar arquivos via MQTT: {e}")

def do_aggregate():
    files = os.listdir(WEIGHTS_FOLDER)
    global shared_state
    if shared_state and shared_state.get("federate"):
        files = os.listdir(shared_state["federate_path"] + str(shared_state["federate_round"]) + "/")
    json_files = [f for f in files if f.endswith('.json') and f != "aggregated_weights.json"]
    json_data = []
    for file in json_files:
        # ! can do the aggregation here to minimize memory usage if needed (for servers with low memory or embedded devices, or even for big models)
        path = WEIGHTS_FOLDER + file
        if shared_state and shared_state.get("federate"):
            path = shared_state["federate_path"] + str(shared_state["federate_round"]) + "/" + file
        with open(path, 'r') as f:
            data = json.load(f)
            json_data.append(data)

    aggregated = {}
    # TODO change handling precision
    if False:
        aggregated["precision"] = "double"
    else:
        aggregated["precision"] = "float"
    aggregated["biases"] = []
    aggregated["weights"] = []

    biaslen = len(json_data[0]["data"]["biases"])
    weightslen = len(json_data[0]["data"]["weights"])

    # ! Innefficient 2*n² loops

    for i in range(biaslen):
        aggregated["biases"].append(0)
        for k in range (len(json_data)):
            # ? is this aggregation policy good?
            aggregated["biases"][i] += float(json_data[k]["data"]["biases"][i])
        aggregated["biases"][i] = aggregated["biases"][i] / len(json_data)

    for i in range(weightslen):
        aggregated["weights"].append(0)
        for k in range (len(json_data)):
            # ? is this aggregation policy good?
            aggregated["weights"][i] += float(json_data[k]["data"]["weights"][i])
        aggregated["weights"][i] = aggregated["weights"][i] / len(json_data)

    aggregated_path = WEIGHTS_FOLDER + "aggregated_weights.json"
    if shared_state and shared_state.get("federate"):
        aggregated_path = shared_state["federate_path"] + str(shared_state["federate_round"]) + "/aggregated_weights.json"

    with open(aggregated_path, 'w') as f:
        json.dump(aggregated, f, indent=4)
    print(f"Pesos agregados salvos no arquivo {aggregated_path}")

def do_server():
    federate = True

    client.on_message = on_message
    client.on_connect = on_connect

    client.subscribe([(TOPIC_RECEIVE_FROM_DEVICES, 0), (TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)])

    client.loop_start()

    federate_path = WEIGHTS_FOLDER + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "/"
    federate_round = 0

    global shared_state
    shared_state["federate_path"] = federate_path
    shared_state["federate_round"] = federate_round
    shared_state["federate"] = federate

    shared_state["max_federate_rounds"] = int(input("\nDigite o número de rodadas que quer fazer o processo federativo: "))

    os.makedirs(federate_path, exist_ok=True)
    os.makedirs(federate_path + str(federate_round) + "/", exist_ok=True)

    # print("Removendo arquivos dos modelos e agregados")
    # files = os.listdir(WEIGHTS_FOLDER)
    # json_files = [f for f in files if f.endswith('.json')]
    # for file in json_files:
    #     os.remove(WEIGHTS_FOLDER + file)

    print("Aguardando 60 segundos para os dispositivos se conectarem...")

    for i in range(6):
        # client.loop()
        client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_join"}))
        sleep(10)
    
    # client.loop()

    if len(federate_clients) < 1:
        print("Nenhum cliente inscrito, encerrando...")
        return

    os.makedirs(federate_path + str(federate_round) + "/", exist_ok=True)

    print(f"Federated learning round {federate_round} iniciado com {len(federate_clients)} clientes.")

    client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_start"}))

    times = 0

    while True:
        sleep(1)
        # client.loop()
        files = os.listdir(federate_path + str(federate_round) + "/")
        json_files = [f for f in files if f.endswith('.json')]
        times += 1
        if len(json_files) == len(federate_clients):
            print("Todos os arquivos recebidos.")
            sleep(1)
            do_aggregate()
            send_mqtt(filepath=federate_path + str(federate_round) + "/" + "aggregated_weights.json")
            sleep(1)
            # files = os.listdir(WEIGHTS_FOLDER)
            # json_files = [f for f in files if f.endswith('.json')]
            # for file in json_files:
            #     os.remove(WEIGHTS_FOLDER + file)
            if (shared_state["max_federate_rounds"] == federate_round):
                print("Número máximo de rodadas atingido, encerrando...")
                break
            federate_round += 1
            shared_state["federate_round"] = federate_round
            os.makedirs(federate_path + str(federate_round) + "/", exist_ok=True)
            print(f"Pesos enviados, iniciando próximo round: {federate_round}")
        elif times > 10:
            print((f"Arquivos recebidos: {len(json_files)} de {len(federate_clients)}"))
            times = 0

    client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_end"}))

def do_parse():
    found_files = [] 
    for root, dirs, files in os.walk(PARSE_FOLDER):
        for file in files:
            if file.endswith('.json') and file != "aggregated_weights.json":
                found_files.append(os.path.join(root, file))
    
    if len(found_files) < 1:
        print("Nenhum arquivo JSON encontrado na pasta de parse.")
        return

    found_files.sort()
        
    print(f"Found {len(found_files)} JSON files:")
    for file in found_files:
        print(f"- {file}")

    json_data = []
    for file in found_files:
        with open(file, 'r') as f:
            try:
                data = json.load(f)
                round_match = re.search(r'/(\d+)/', file)
                if round_match:
                    data["round"] = int(round_match.group(1))
                else:
                    data["round"] = 6
  
                data["metrics"] = data["data"]["metrics"]
                data["client"] = data["data"]["client"]
                data["data"] = None
                json_data.append(data)
                print(data)
            except json.JSONDecodeError as e:
                print(f"Error parsing {file}: {e}")

    print("Dados parseados com sucesso.")

    # List of metrics to plot - add or remove as needed
    metrics_to_plot = ["meanSqrdError", "accuracy", "precision", "recall", "f1Score"]
    
    for metric in metrics_to_plot:
        try:
            plot_metrics(json_data, metric)
        except Exception as e:
            print(f"Error plotting {metric}: {e}")
    

def plot_metrics(json_data, metric_name="meanSqrdError"):
    """
    Plot the evolution of a specified metric across clients.
    
    Parameters:
    - json_data: List of parsed JSON objects with metrics
    - metric_name: The name of the metric to plot (default is "meanSqrdError")
    """
    
    # Group data by client
    client_data = defaultdict(list)
    
    # Extract round number from filename or data
    for item in json_data:
        client = item["client"]
        # If the metric exists, add it to the client's data
        if metric_name in item["metrics"]:
            metric_value = float(item["metrics"][metric_name])
            # Try to extract round number from received_time or file path
            round_num = item.get("round", 0)  # Default to 0 if not found
            client_data[client].append((round_num, metric_value))
    
    if not client_data:
        print(f"No data found for metric: {metric_name}")
        return
        
    # Create plot
    plt.figure(figsize=(10, 6))
    
    # Plot data for each client
    for client, points in client_data.items():
        # Sort by round number
        points.sort(key=lambda x: x[0])
        rounds = [p[0] for p in points]
        values = [p[1] for p in points]
        plt.plot(rounds, values, 'o-', label=f"Client {client}")
    
    plt.title(f"Evolution of {metric_name} across rounds")
    plt.xlabel("Round")
    plt.ylabel(metric_name)
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Save plot
    filename = f"plot_{metric_name}.png"
    plt.savefig(filename)
    print(f"Plot saved as {filename}")
    
    # Show plot
    plt.show()

# Configuração do cliente MQTT
client = mqtt.Client()
client.connect(BROKER_IP, 1883, 60)

# Interact through the shell but without interrupting the MQTT loop
try:
    while True:
        user_input = input("Digite: \n 'send' \t para agregar os modelos disponíveis e enviar aos dispositivos \n 'request' \t para solicitar modelos dos dispositivos \n 'listen' \t para montar um servidor que apenas escuta mensagens e salva \n 'federate' \t para abrir um servidor federado \n 'parse' \t para dar parse  nos dados e dar um output de forma mais útil \n Escreva a opção desejada: ").strip().lower()
        if user_input == 'send':
            do_aggregate()
            send_mqtt(filepath=WEIGHTS_FOLDER + "aggregated_weights.json")
        elif user_input == 'listen':
            client.on_message = on_message
            client.on_connect = on_connect

            # Inscreve-se nos tópicos de interesse
            # client.subscribe([(TOPIC_RECEIVE_FROM_DEVICES, 0), (TOPIC_SEND_TO_DEVICES, 0)])
            client.subscribe([(TOPIC_RECEIVE_FROM_DEVICES, 0)])

            print("Escutando mensagens MQTT... Pressione Ctrl+C para sair.")
            client.loop_forever()
        elif user_input == 'request':
            request_json = {
                "command": "request_model",
            }
            client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps(request_json))
            print("Enviando solicitação de pesos para os dispositivos...")

        elif user_input == 'federate':
            do_server()
        elif user_input == 'parse':
            do_parse()
        else:
            print("Comando inválido. Tente novamente.")
except KeyboardInterrupt:
    print("Saindo...")
finally:
    client.disconnect()
    print("Cliente MQTT desconectado.")