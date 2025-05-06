import json
import paho.mqtt.client as mqtt
from datetime import datetime

# Variável para armazenar os dados recebidos
received_data = []  # Lista para armazenar as partes do arquivo JSON com timestamps
json_filename = ''  # Nome do arquivo JSON será baseado no espID
start_time = None  # Tempo de início da transmissão
end_time = None    # Tempo de término da transmissão

# Callback quando o cliente se conecta ao broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Conectado ao broker MQTT!")
        # Assinar o tópico para todos os ESPs
        client.subscribe("esp32/ai")  # O "+" é um curinga que pega esp01, esp02, etc.
    else:
        print(f"Falha na conexão. Código de erro: {rc}")

# Callback para lidar com a mensagem recebida
def on_message(client, userdata, message):
    global received_data, json_filename, start_time, end_time

    # Decodificar a mensagem recebida
    msg = message.payload.decode('utf-8')

    # Extrair o espID do tópico
    topic_parts = message.topic.split('/')
    espID = topic_parts[1]  # "esp01", "esp02", etc.

    # Definir o nome do arquivo com base no espID
    json_filename = espID + '.json'

    if msg == "INICIO_TRANSMISSAO":
        # Reiniciar a lista de dados e registrar o tempo de início
        received_data = []
        start_time = datetime.now()
        print(f"Iniciando a recepção de pesos do {espID}...")

    elif msg == "FIM_TRANSMISSAO":
        # Registrar o tempo de término e salvar os dados no arquivo JSON
        end_time = datetime.now()
        print(f"Transmissão de pesos do {espID} concluída. Salvando arquivo...")
        save_to_json_file()

    else:
        # Adicionar a parte recebida à lista de dados com o timestamp
        timestamp = datetime.now().isoformat()  # Registrar o tempo de recepção
        print(f"Recebendo parte dos pesos do {espID} às {timestamp}...")
        received_data.append({"timestamp": timestamp, "data": msg})

# Função para salvar os dados no arquivo JSON
def save_to_json_file():
    global received_data, json_filename, start_time, end_time

    # Calcular o tempo total de recepção
    total_time = (end_time - start_time).total_seconds() if start_time and end_time else None

    # Adicionar o tempo total de recepção ao JSON final
    output_data = {
        "total_reception_time_seconds": total_time,
        "received_parts": received_data
    }

    # Tentar salvar o JSON no arquivo
    try:
        with open(json_filename, 'w') as json_file:
            json.dump(output_data, json_file, indent=4)
        print(f"Arquivo JSON salvo como {json_filename}")

    except json.JSONDecodeError as e:
        print(f"Erro ao decodificar JSON: {e}")
        print(f"Dados recebidos: {received_data}")

# Configuração do cliente MQTT
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

# Conectar ao broker MQTT
broker_ip = "127.0.0.1"  # Substitua pelo IP do seu broker
client.connect(broker_ip, 1883, 60)

# Manter o cliente em loop para escutar mensagens
client.loop_forever()



