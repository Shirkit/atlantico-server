import json
import os
import paho.mqtt.client as mqtt
import time

# Definição do broker MQTT
# UFBA 10.131.12.37
# CASA 192.168.15.11

BROKER_IP = "10.131.12.37"  # IP do  broker MQTT
MQTT_TOPIC_WEIGHTS = "esp32/model_weights"
MQTT_TOPIC_BIASES = "esp32/model_biases"

# Caminhos dos arquivos de pesos e bias
WEIGHTS_FILE_PATH = "/home/claudio/atlantico/pesos/model_weights.txt"
BIASES_FILE_PATH = "/home/claudio/atlantico/pesos/model_biases.txt"

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
        weights_data = ler_arquivo(WEIGHTS_FILE_PATH)
        biases_data = ler_arquivo(BIASES_FILE_PATH)

        if weights_data:
            print("Enviando model_weights.txt via MQTT...")
            enviar_dados_mqtt(client, MQTT_TOPIC_WEIGHTS, weights_data)

        if biases_data:
            print("Enviando model_biases.txt via MQTT...")
            enviar_dados_mqtt(client, MQTT_TOPIC_BIASES, biases_data)

        # Desconectar do broker MQTT
        client.disconnect()
    except Exception as e:
        print(f"Erro ao enviar arquivos via MQTT: {e}")

# Função auxiliar para enviar os dados em chunks via MQTT
def enviar_dados_mqtt(client, topic, data, chunk_size=128):
    print(f"Enviando dados para o tópico {topic}...")
    client.publish(topic, "INICIO_TRANSMISSAO")

    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        client.publish(topic, chunk)
        print(f"Enviado chunk: {chunk}")
        time.sleep(0.5)  # Pequeno delay para evitar sobrecarga

    client.publish(topic, "FIM_TRANSMISSAO")

# Executar a função de envio
if __name__ == "__main__":
    enviar_arquivos_mqtt()
