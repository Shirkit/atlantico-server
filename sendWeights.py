import json
import os
import paho.mqtt.client as mqtt
import time

# Definição do broker MQTT
# UFBA 10.131.12.37
# CASA 192.168.15.11

BROKER_IP = "192.168.15.13"  # IP do  broker MQTT
MQTT_TOPIC_WEIGHTS = "esp32/model_weights"
MQTT_TOPIC_BIASES = "esp32/model_biases"
MQTT_TOPIC_AI = "esp32/ai"

# Caminhos dos arquivos de pesos e bias
WEIGHTS_FILE_PATH = "./pesos/model_weights.txt"
BIASES_FILE_PATH = "./pesos/model_biases.txt"
NEW_WEIGHTS_FILE_PATH = "./pesos/new_weights.json"
WEIGHTS_PATH = "model_biases_received.txt"

# Função para ler os arquivos de pesos e bias
def ler_arquivo(caminho_arquivo):
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

# Função para enviar os arquivos via MQTT
def enviar_arquivos_mqtt():
    client = mqtt.Client()

    try:
        # Conectar ao broker MQTT
        client.connect(BROKER_IP, 1883, 60)

        # Ler os arquivos
        # weights_data = ler_arquivo(WEIGHTS_FILE_PATH)
        # biases_data = ler_arquivo(BIASES_FILE_PATH)
        new_weights = ler_arquivo(WEIGHTS_PATH)

        # if weights_data:
        #     print("Enviando model_weights.txt via MQTT...")
        #     enviar_dados_mqtt(client, MQTT_TOPIC_WEIGHTS, weights_data)

        # if biases_data:
        #     print("Enviando model_biases.txt via MQTT...")
        #     enviar_dados_mqtt(client, MQTT_TOPIC_BIASES, biases_data)

        if new_weights:
            print("Enviando new_weights.txt via MQTT...")
            enviar_dados_mqtt(client, MQTT_TOPIC_AI, new_weights)

        # Desconectar do broker MQTT
        client.disconnect()
    except Exception as e:
        print(f"Erro ao enviar arquivos via MQTT: {e}")

# Função auxiliar para enviar os dados em chunks via MQTT
def enviar_dados_mqtt(client, topic, data, chunk_size=16000):
    print(f"Enviando dados para o tópico {topic}...")
    # client.publish(topic, "INICIO_TRANSMISSAO")

    time.sleep(1)

    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        client.publish(topic, chunk)
        print(f"Enviado chunk: {chunk}")
        time.sleep(1)  # Pequeno delay para evitar sobrecarga

    time.sleep(1)

    # client.publish(topic, "FIM_TRANSMISSAO")

# Executar a função de envio
if __name__ == "__main__":
    enviar_arquivos_mqtt()
