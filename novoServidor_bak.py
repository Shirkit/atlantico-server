import json
import paho.mqtt.client as mqtt
from datetime import datetime
from time import sleep
import os
import uuid
import math
from parser import do_parse

# Variável para armazenar os dados recebidos
shared_state = {}

print('\33]0;Escolha comando\a', end='', flush=True)

BROKER_IP = "127.0.0.1"
TOPIC_RECEIVE_FROM_DEVICES = "esp32/fl/model/push"
TOPIC_RECEIVE_FROM_DEVICES_RAW = "esp32/fl/model/rawpush/+"
TOPIC_SEND_TO_DEVICES = "esp32/fl/model/pull"
TOPIC_RECEIVE_COMMANDS_FROM_DEVICES = "esp32/fl/commands/push"
TOPIC_SEND_COMMANDS_TO_DEVICES = "esp32/fl/commands/pull"
TOPIC_RESUME_TO_DEVICES = "esp32/fl/model/resume"
PARSE_FOLDER = "parse/"
WEIGHTS_FOLDER = "weights/"
METRICS_FOLDER = "metrics/"

# ready_clients = []

def dump(obj):
  for attr in dir(obj):
    print("obj.%s = %r" % (attr, getattr(obj, attr)))

def on_connect(client, userdata, flags, rc):
    if rc != 0:
        print(f"Falha na conexão. Código de erro: {rc}")

# Função chamada quando uma mensagem MQTT é recebida
def on_message(client, userdata, message):
    try:
        topic = message.topic
        topic_parts = message.topic.split('/')
        print("Mensagem recebida no tópico " + topic)
        if topic_parts[3] == "rawpush":
            global shared_state
            clientname = topic_parts[4]
            filepath = ""
            if shared_state and shared_state.get("federate") is True:
                filepath = shared_state["federate_path"] + str(shared_state["federate_round"]) + "/" + clientname + ".nn"
            else:
                filepath = WEIGHTS_FOLDER + clientname + ".nn"
            
            with open(filepath, 'wb') as f:
                f.write(message.payload)

            if os.path.exists(os.path.dirname(filepath.replace(".nn", ".json"))):
                if shared_state.get("waiting_for") and clientname in shared_state["waiting_for"]:
                    shared_state["waiting_for"].remove(clientname)
        else:
            payload = message.payload.decode("utf-8")
            if (topic_parts[2] == "model"):
                save_to_json_file(payload)
            elif (topic_parts[2] == "commands"):
                parse_command(payload)
    except UnicodeDecodeError as e:
        print("Erro ao decodificar a mensagem recebida:")
        print(message.payload)
        print(e)
    except json.JSONDecodeError as e:
        print("Erro ao decodificar JSON da mensagem:")
        print(message.payload)
        print(e)

def parse_command(payload):
    msg = json.loads(payload)
    global shared_state
    if "command" in msg and "federate" in shared_state and shared_state["federate"] is True:
        if msg["command"] == "join":
            if (msg["client"] not in shared_state["federate_clients"]):
                shared_state["federate_clients"].append(msg["client"])
                print(f"Cliente {msg['client']} se juntou ao servidor. Total de clientes: {len(shared_state['federate_clients'])}")
        elif msg["command"] == "leave":
            if (msg["client"] in shared_state["federate_clients"]):
                shared_state["federate_clients"].remove(msg["client"])
                print(f"Cliente {msg['client']} saiu do servidor.")
        elif msg["command"] == "resume":
            if (msg["client"] in shared_state["federate_clients"]):
                print(f"Cliente {msg['client']} está pronto para continuar.")
                try:
                    send_mqtt(topic=TOPIC_SEND_COMMANDS_TO_DEVICES, data=json.dumps({"command": "federate_resume", "client": msg["client"], "round": shared_state["federate_round"] }, separators=(',', ':')))
                    send_mqtt(topic=TOPIC_RESUME_TO_DEVICES, filepath=shared_state["federate_path"] + str(shared_state["federate_round"] - 1) + "/" + "aggregated_weights.json")
                except Exception as e:
                    print(f"Erro ao enviar arquivo de pesos: {e}")
        elif msg["command"] == "alive":
            if (msg["client"] in shared_state["federate_clients"]):
                print(f"Cliente {msg['client']} está ativo.")
    elif msg["command"] == "alive":
        if msg['client'] not in shared_state["alive"]:
            shared_state["alive"].append(msg["client"])
            shared_state["alive"].sort()
        print(f"Total de Clientes ativos: {len(shared_state["alive"])} {shared_state["alive"]}")
    else:
        print("Comando não reconhecido ou federated learning não está ativo.")
        print(payload)

                
        # elif msg["command"] == "ready":
        #     if (msg["client"] not in ready_clients) and (msg["client"] in federate_clients):
        #         ready_clients.append(msg["client"])
        #         print(f"Cliente {msg['client']} está pronto.")

def save_to_json_file(data):
    try:
        loaded = json.loads(data)
        output_data = {
            "received_time": datetime.now().isoformat(),
            "data": loaded,
        }
        clientname = output_data["data"]["client"]
        filepath = ""

        global shared_state

        if os.path.exists(filepath.replace(".json", ".nn")):
            if shared_state.get("waiting_for") and clientname in shared_state["waiting_for"]:
                shared_state["waiting_for"].remove(clientname)

        if shared_state and shared_state.get("federate") is True:
            filepath = shared_state["federate_path"] + str(shared_state["federate_round"]) + "/" + clientname + ".json"
        else:
            filepath = WEIGHTS_FOLDER + clientname + ".json"
        try:
            with open(filepath, 'x') as json_file:
                json.dump(output_data, json_file, indent=4, separators=(',', ':'))
            print(f"Arquivo JSON salvo como {filepath}")
        except FileExistsError:
            # Por algum motivo recebemos o mesmo arquivo duas vezes, ignorando
            pass

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

def send_mqtt(data = None, filepath = None, topic = TOPIC_SEND_TO_DEVICES):
    try:
        if filepath:
            new_weights = read_file(filepath)
            if new_weights:
                print("Enviando arquivo " + filepath + " via MQTT...")
                client.publish(topic, new_weights)
        if data:
            print("Enviando dados via MQTT...")
            client.publish(topic, data)
    except Exception as e:
        print(f"Erro ao enviar arquivos via MQTT: {e}")

def do_aggregate(round=-1):
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
    if round >= 0:
        aggregated["round"] = round

    biaslen = len(json_data[0]["data"]["biases"])
    weightslen = len(json_data[0]["data"]["weights"])

    skip = []
    for i in range(len(json_data)):
        if json_data[i]["data"]["metrics"]["meanSqrdError"] is None or math.isnan(json_data[i]["data"]["metrics"]["meanSqrdError"]):
            skip.append(i)
            continue

    # ! Innefficient 2*n² loops

    for i in range(biaslen):
        aggregated["biases"].append(0)
        for k in range (len(json_data)):
            if k in skip:
                continue
            # ? is this aggregation policy good?
            aggregated["biases"][i] += float(json_data[k]["data"]["biases"][i])
        aggregated["biases"][i] = aggregated["biases"][i] / (len(json_data) - len(skip))

    for i in range(weightslen):
        aggregated["weights"].append(0)
        for k in range (len(json_data)):
            if k in skip:
                continue
            # ? is this aggregation policy good?
            aggregated["weights"][i] += float(json_data[k]["data"]["weights"][i])
        aggregated["weights"][i] = aggregated["weights"][i] / (len(json_data) - len(skip))

    aggregated_path = WEIGHTS_FOLDER + "aggregated_weights.json"
    if shared_state and shared_state.get("federate"):
        aggregated_path = shared_state["federate_path"] + str(shared_state["federate_round"]) + "/aggregated_weights.json"

    with open(aggregated_path, 'w') as f:
        json.dump(aggregated, f, indent=4, separators=(',', ':'))
    print(f"Pesos agregados salvos no arquivo {aggregated_path}")

def do_server():
    federate = True

    client.on_message = on_message
    client.on_connect = on_connect

    client.subscribe([(TOPIC_RECEIVE_FROM_DEVICES, 0), (TOPIC_RECEIVE_FROM_DEVICES_RAW, 0), (TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)])

    client.loop_start()

    federate_path = WEIGHTS_FOLDER + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "/"
    federate_round = 0

    global shared_state
    shared_state["federate_path"] = federate_path
    shared_state["federate_round"] = federate_round
    shared_state["federate"] = federate
    shared_state["federate_clients"] = []

    shared_state["max_federate_rounds"] = int(input("\nDigite o número de rodadas que quer fazer o processo federativo: "))

    expected_clients = int(input("Digite o número de clientes que você espera se conectar: "))

    os.makedirs(federate_path, exist_ok=True)
    os.makedirs(federate_path + str(federate_round) + "/", exist_ok=True)

    # print("Removendo arquivos dos modelos e agregados")
    # files = os.listdir(WEIGHTS_FOLDER)
    # json_files = [f for f in files if f.endswith('.json')]
    # for file in json_files:
    #     os.remove(WEIGHTS_FOLDER + file)

    print("Aguardando 10 segundos para os dispositivos se conectarem...")

    for i in range(3):
        # client.loop()
        client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_join"}, separators=(',', ':')))
        sleep(3)
 
    # client.loop()

    if len(shared_state["federate_clients"]) < 1:
        print("Nenhum cliente inscrito, encerrando...")
        return

    if len(shared_state["federate_clients"]) < expected_clients:
        print("Número de clientes inscritos é menor que o esperado, encerrando...")
        for i in range(5):
            client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_unsubscribe"}, separators=(',', ':')))
            sleep(1)
        return

    os.makedirs(federate_path + str(federate_round) + "/", exist_ok=True)

    print(f"Federated learning round {federate_round} iniciado com {len(shared_state["federate_clients"])} clientes.")
    
    start_command = {
        "command": "federate_start",
        "config": {
            # "layers": [3, 192, 96, 48, 24, 12, 6],
            # "layers": [3, 54, 27, 13, 6],
            "layers": [3, 9, 6],
            # "actvFunctions": [1, 1, 1, 1, 1, 6],
            # "actvFunctions": [1, 1, 1, 6],
            "actvFunctions": [1, 6],
            "epochs": 1,
            "learningRateOfWeights": 0.3333 / 12.0,
            "learningRateOfBiases": 0.0666 / 12.0,
            "randomSeed": 10
        }
    }

    shared_state["waiting_for"] = []

    for waiting in shared_state["federate_clients"]:
        shared_state["waiting_for"].append(waiting)

    print(f"Configuração do processo federativo: {start_command["config"]}")
    client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps(start_command, separators=(',', ':')))

    device_count = len(shared_state["federate_clients"])

    start_command["config"]["devices"] = shared_state["federate_clients"]
    start_command["config"]["devices"].sort()
    neurons = 0
    for i in range (len(start_command["config"]["layers"]) - 1):
        neurons = neurons + start_command["config"]["layers"][i] * start_command["config"]["layers"][i+1]
    start_command["config"]["neurons"] = neurons
    start_command["config"]["device_count"] = device_count
    start_command["config"]["bits"] = "32"
    start_command["config"]["run"] = "X"

    json.dump(start_command, open(federate_path + "/config.json", 'w'), indent=4, separators=(',', ':'))

    times = 0

    while True:
        sleep(1)
        # client.loop()
        # files = os.listdir(federate_path + str(federate_round) + "/")
        # json_files = [f for f in files if f.endswith('.json')]
        times += 1
        # if len(json_files) == len(shared_state["federate_clients"]):
        if len(shared_state["waiting_for"]) == 0:
            if (shared_state["max_federate_rounds"] == (federate_round+1)):
                print("Número máximo de rodadas atingido, encerrando...")
                do_aggregate(federate_round)
                break
            print("Todos os arquivos recebidos.")
            sleep(1)
            do_aggregate(federate_round) # TODO Explosão do Gradiente lança um erro e crasha o processo federativo
            send_mqtt(filepath=federate_path + str(federate_round) + "/" + "aggregated_weights.json")
            sleep(1)
            # files = os.listdir(WEIGHTS_FOLDER)
            # json_files = [f for f in files if f.endswith('.json')]
            # for file in json_files:
            #     os.remove(WEIGHTS_FOLDER + file)
            federate_round += 1
            shared_state["federate_round"] = federate_round
            os.makedirs(federate_path + str(federate_round) + "/", exist_ok=True)
            shared_state["waiting_for"].clear()
            for waiting in shared_state["federate_clients"]:
                shared_state["waiting_for"].append(waiting)
            print(f"Pesos enviados, iniciando próximo round: {federate_round}")
        elif times > 20:
            print(f"Arquivos recebidos: {device_count - len(shared_state["waiting_for"])} de {device_count}. Aguardando pelos clientes: {shared_state["waiting_for"]}")
            times = 0
            # client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_waiting", "clients":shared_state["waiting_for"]}, separators=(',', ':')))
            # client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_waiting", "for":waiting}, separators=(',', ':')))

    federate_round += 1
    shared_state["federate_round"] = federate_round
    os.makedirs(federate_path + str(federate_round) + "/", exist_ok=True)

    client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_end"}, separators=(',', ':')))

    sleep(5)

    client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_unsubscribe"}, separators=(',', ':')))

    json.dump({}, open(federate_path + "/done.json", 'x'), indent=4, separators=(',', ':'))

# Configuração do cliente MQTT
client = mqtt.Client(client_id="Notebook-" + str(uuid.uuid4()), clean_session=True)
client.connect(BROKER_IP, 1883, 60)

# Interact through the shell but without interrupting the MQTT loop
try:
    while True:
        user_input = input("Digite: \n 'send' \t para agregar os modelos disponíveis e enviar aos dispositivos \n 'request' \t para solicitar modelos dos dispositivos \n 'listen' \t para montar um servidor que apenas escuta mensagens e salva \n 'federate' \t para abrir um servidor federado \n 'parse' \t para dar parse  nos dados e dar um output de forma mais útil \n 'unsub' \t Força encerramento do processo federativo nos clientes Escreva a opção desejada: ").strip().lower()
        if user_input == 'send':
            do_aggregate()
            send_mqtt(filepath=WEIGHTS_FOLDER + "aggregated_weights.json")
        elif user_input == 'listen':
            client.on_message = on_message
            client.on_connect = on_connect

            # Inscreve-se nos tópicos de interesse
            # client.subscribe([(TOPIC_RECEIVE_FROM_DEVICES, 0), (TOPIC_SEND_TO_DEVICES, 0)])
            client.subscribe([(TOPIC_RECEIVE_FROM_DEVICES, 0), (TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)])

            print("Escutando mensagens MQTT... Pressione Ctrl+C para sair.")
            print('\33]0;Listen - Servidor Federado\a', end='', flush=True)
            client.loop_forever()
        elif user_input == 'request':
            request_json = {
                "command": "request_model",
            }
            client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps(request_json, separators=(',', ':')))
            print("Enviando solicitação de pesos para os dispositivos...")

        elif user_input == 'federate':
            print('\33]0;Servidor Federado\a', end='', flush=True)
            do_server()
        elif user_input == 'parse':
            do_parse(PARSE_FOLDER, METRICS_FOLDER)
        elif user_input == 'unsub':
            client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_unsubscribe"}, separators=(',', ':')))
        elif user_input == 'alive':
            print("Enviando sinal de vida para os dispositivos...")
            client.on_message = on_message
            client.on_connect = on_connect
            client.subscribe([(TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)])
            shared_state["alive"] = []
            client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_alive"}, separators=(',', ':')))
            client.loop_forever()
            sleep(2)
            client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_alive"}, separators=(',', ':')))
            sleep(2)
            client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, json.dumps({"command":"federate_alive"}, separators=(',', ':')))
        else:
            print("Comando inválido. Tente novamente.")
except KeyboardInterrupt:
    print("Saindo...")
finally:
    client.disconnect()
    print("Cliente MQTT desconectado.")