import json
import paho.mqtt.client as mqtt
from datetime import datetime
from pprint import pprint
import os

# Variável para armazenar os dados recebidos
received_data = []  # Lista para armazenar as partes do arquivo JSON com timestamps
json_filename = ''  # Nome do arquivo JSON será baseado no espID
start_time = None  # Tempo de início da transmissão
end_time = None    # Tempo de término da transmissão

BROKER_IP = "127.0.0.1"
TOPIC_RECEIVE_FROM_DEVICES = "esp32/fl/push/+"
TOPIC_SEND_TO_DEVICES = "esp32/fl/pull/esp01"
WEIGHTS_FOLDER = "pesos/"

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
    espID = topic_parts[3]
    if not espID:
        print("Erro: espID não encontrado no tópico.")
        return

    if mqtt.topic_matches_sub(TOPIC_RECEIVE_FROM_DEVICES, topic):
        # save_file(payload, client)
        save_to_json_file(payload, espID)

def save_to_json_file(data, clientname):
    try:
        output_data = {
            "received_time": datetime.now().isoformat(),
            "client_name": clientname,
            "data": json.loads(data),
        }

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
    json_files = [f for f in files if f.endswith('.json') and f != "aggregated_weights.json"]
    json_data = []
    for file in json_files:
        # ! can do the aggregation here to minimize memory usage if needed (for servers with low memory or embedded devices, or even for big models)
        with open(WEIGHTS_FOLDER + file, 'r') as f:
            data = json.load(f)
            json_data.append(data)

    aggregated = {}
    # TODO change handling precision
    if True:
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
        aggregated["biases"][i] = str(aggregated["biases"][i] / len(json_data))

    for i in range(weightslen):
        aggregated["weights"].append(0)
        for k in range (len(json_data)):
            # ? is this aggregation policy good?
            aggregated["weights"][i] += float(json_data[k]["data"]["weights"][i])
        aggregated["weights"][i] = str(aggregated["weights"][i] / len(json_data))

    with open(WEIGHTS_FOLDER + "aggregated_weights.json", 'w') as f:
        json.dump(aggregated, f, indent=4)
    print(f"Pesos agregados salvos no arquivo {WEIGHTS_FOLDER}aggregated_weights.json")

# Configuração do cliente MQTT
client = mqtt.Client()
client.connect(BROKER_IP, 1883, 60)

# Interact through the shell but without interrupting the MQTT loop
try:
    while True:
        user_input = input("Digite 'send' para enviar dados, 'aggregate' para agregar pesos ou 'listen' para escutar mensagens: ").strip().lower()
        if user_input == 'send':
            send_mqtt(filepath=WEIGHTS_FOLDER + "aggregated_weights.json")
        elif user_input == 'aggregate':
            do_aggregate()
        elif user_input == 'listen':
            client.on_message = on_message
            client.on_connect = on_connect

            # Inscreve-se nos tópicos de interesse
            client.subscribe([(TOPIC_RECEIVE_FROM_DEVICES, 0), (TOPIC_SEND_TO_DEVICES, 0)])

            print("Escutando mensagens MQTT... Pressione Ctrl+C para sair.")
            client.loop_forever()
        else:
            print("Comando inválido. Tente novamente.")
except KeyboardInterrupt:
    print("Saindo...")
finally:
    client.disconnect()
    print("Cliente MQTT desconectado.")