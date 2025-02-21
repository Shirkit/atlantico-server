import paho.mqtt.client as mqtt
import os

# Configuração do broker MQTT
BROKER_IP = "10.131.12.37"
TOPIC_WEIGHTS = "esp32/model_weights"
TOPIC_BIASES = "esp32/model_biases"

# Dicionário para armazenar os dados recebidos antes de salvar
data_buffer = {
    TOPIC_WEIGHTS: [],
    TOPIC_BIASES: []
}

# Função chamada quando uma mensagem MQTT é recebida
def on_message(client, userdata, message):
    global data_buffer

    payload = message.payload.decode("utf-8")
    topic = message.topic

    if payload == "INICIO_TRANSMISSAO":
        print(f"[{topic}] Início da transmissão detectado.")
        data_buffer[topic] = []  # Limpa buffer para novo arquivo

    elif payload == "FIM_TRANSMISSAO":
        print(f"[{topic}] Fim da transmissão detectado. Salvando arquivo...")
        save_file(topic, data_buffer[topic])

    else:
        # Adiciona o chunk recebido ao buffer
        data_buffer[topic].append(payload)

# Função para salvar os arquivos recebidos
def save_file(topic, data_chunks):
    file_path = "model_weights_received.txt" if topic == TOPIC_WEIGHTS else "model_biases_received.txt"

    # Junta os chunks e salva o arquivo
    with open(file_path, "w") as file:
        file.write("".join(data_chunks))

    print(f"Arquivo salvo: {file_path}")

# Configuração do cliente MQTT
client = mqtt.Client()
client.on_message = on_message
client.connect(BROKER_IP, 1883, 60)

# Inscreve-se nos tópicos de interesse
client.subscribe([(TOPIC_WEIGHTS, 0), (TOPIC_BIASES, 0)])

print("Escutando mensagens MQTT... Pressione Ctrl+C para sair.")
client.loop_forever()
