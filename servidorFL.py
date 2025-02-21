import json
import os
import paho.mqtt.client as mqtt
import time

# Lista de dispositivos disponíveis (ajuste conforme necessário)
dispositivos_disponiveis = ['esp01', 'esp02', 'esp03']

# Função para selecionar quais dispositivos participarão da agregação
def selecionar_dispositivos():
    print("Dispositivos disponíveis: ", dispositivos_disponiveis)
    dispositivos_selecionados = input("Digite os dispositivos separados por vírgula que irão participar da agregação: ")
    return dispositivos_selecionados.split(',')

# Função para receber pesos de um dispositivo lendo os arquivos da pasta local
def receber_pesos(dispositivo):
    file_path = f'/home/claudio/atlantico/pesos/{dispositivo}.json'
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as file:
                pesos = json.load(file)
                return pesos
        else:
            print(f"Arquivo de pesos para {dispositivo} não encontrado.")
            return None
    except Exception as e:
        print(f"Erro ao ler pesos do {dispositivo}: {e}")
        return None

# Função para agregar pesos usando FedAvg com suporte para tamanhos diferentes
def agregar_pesos(pesos_dispositivos):
    # Estrutura para armazenar os pesos agregados
    pesos_agregados = {}

    # Para cada tipo de peso, calcular a média ponderada para cada posição
    for key in pesos_dispositivos[0].keys():
        # Encontra o comprimento máximo do array de pesos para essa chave
        max_length = max(len(pesos[key]) for pesos in pesos_dispositivos)
        soma_pesos = [0] * max_length
        contagem = [0] * max_length

        # Somar os pesos na posição correspondente de cada dispositivo
        for pesos in pesos_dispositivos:
            for i in range(len(pesos[key])):
                soma_pesos[i] += pesos[key][i]
                contagem[i] += 1

        # Calcular a média para cada posição com a contagem total
        pesos_agregados[key] = [soma_pesos[i] / contagem[i] if contagem[i] > 0 else 0 for i in range(max_length)]

    return pesos_agregados

# Função para salvar pesos agregados em um arquivo
def salvar_pesos_agregados_em_arquivo(pesos_agregados, nome_arquivo="pesos_agregados.json"):
    with open(nome_arquivo, 'w') as f:
        json.dump(pesos_agregados, f, indent=4)
    print(f"Pesos agregados salvos no arquivo {nome_arquivo}")

# Função para formatar os pesos com 6 casas decimais
def formatar_pesos(pesos_agregados):
    for key in pesos_agregados:
        pesos_agregados[key] = [format(p, '.6f') for p in pesos_agregados[key]]
    return pesos_agregados

# Função para enviar os pesos agregados via MQTT para um tópico único
def enviar_pesos_via_mqtt(pesos_agregados):
    broker_ip = "192.168.15.11"  # IP do seu broker MQTT
    client = mqtt.Client()

    # Conectar ao broker MQTT
    client.connect(broker_ip, 1883, 60)

    # Formatar os pesos com 6 casas decimais
    pesos_agregados_formatados = formatar_pesos(pesos_agregados)

    # Converter os pesos agregados para JSON string
    pesos_json = json.dumps(pesos_agregados_formatados)

    # Definir o tópico MQTT único para todos os ESP32
    mqtt_topic = "esp32/weights_agregado"

    print(f"Enviando pesos agregados para o tópico {mqtt_topic} via MQTT...")

    # Enviar o sinal de início da transmissão antes de enviar os dados
    client.publish(mqtt_topic, "INICIO_TRANSMISSAO")

    # Enviar o arquivo JSON em chunks
    chunk_size = 128  # Ajuste conforme necessário
    for i in range(0, len(pesos_json), chunk_size):
        chunk = pesos_json[i:i + chunk_size]
        client.publish(mqtt_topic, chunk)
        print(f"Enviado chunk: {chunk}")
        time.sleep(0.5)  # 500ms de atraso (ajuste conforme necessário)

    # Enviar sinal de fim de transmissão
    client.publish(mqtt_topic, "FIM_TRANSMISSAO")

    # Desconectar do broker MQTT
    client.disconnect()

# Função principal
def main():
    dispositivos_selecionados = selecionar_dispositivos()
    pesos_dispositivos = []

    # Receber pesos de cada dispositivo selecionado
    for dispositivo in dispositivos_selecionados:
        print(f"Recebendo pesos de {dispositivo}...")
        pesos = receber_pesos(dispositivo)
        if pesos:
            pesos_dispositivos.append(pesos)

    # Verificar se há pesos suficientes para agregar
    if len(pesos_dispositivos) > 0:
        # Agregar pesos
        print("Agregando pesos...")
        pesos_agregados = agregar_pesos(pesos_dispositivos)
        print("Pesos agregados:", pesos_agregados)

        # Salvar pesos agregados em um arquivo
        salvar_pesos_agregados_em_arquivo(pesos_agregados)

        # Enviar pesos agregados para o tópico único via MQTT
        enviar_pesos_via_mqtt(pesos_agregados)
    else:
        print("Nenhum peso recebido, encerrando processo de agregação.")

if __name__ == "__main__":
    main()




