# Atlantico Server - Federated Learning Server

Este repositório contém a implementação de um servidor para aprendizado federado (Federated Learning), focado no recebimento, agregação e envio de pesos de modelos neurais em um ambiente distribuído.

## Estrutura do Projeto

```
atlantico-server/
├── novoServidor.py       # Script central que roda todos as funcionalidades
├── metrics/              # Saída dos gráficos dos resultados contidos na pasta 'parse'
├── parse/                # Aqui coloca-se o resultado do processo federativo para cálculo das métricas 
└── weights/              # Pasta que contém o output dos pesos recebidos e do processo federativo     
```

## 🚀 Funcionalidades

- Recebimento de pesos de múltiplos clientes ESP32
- Agregação de modelos através de média ponderada
- Envio de pesos globais agregados aos dispositivos
- Orquestração de rodadas de treinamento federado
- Geração de visualizações e métricas de desempenho
- Análise comparativa entre diferentes dispositivos e rodadas

## 🛠️ Requisitos

- Python 3.13 (tecnicamente pode rodar em 3.8 ou superior)
- Bibliotecas:
  - `paho-mqtt`
  - `seaborn`
  - `numpy`
  - `matplotlib`
- Broker MQTT


Instale as dependências através do pip:

```
pip install paho-mqtt matplotlib seaborn numpy
```

Caso esteja utilizando um ambiente virtual, ative-o antes de executar a instalação:

```
python -m venv venv
```

Certifique-se de ter um broker MQTT executando (por exemplo, Mosquitto):

```
# Instalar o Mosquitto (Ubuntu/Debian)
sudo apt-get install mosquitto mosquitto-clients

# Iniciar o serviço
sudo systemctl start mosquitto
```

## 💻 Como Executar

### 1. Iniciar o servidor federado

python3 server.py

### 2. Rode o comando desejado

Ao executar o servidor, você terá acesso aos seguintes comandos:

- **federate**: Inicia um processo completo de aprendizado federado
- **parse**: Analisa os dados armazenados e gera visualizações gráficas
- *send*: Agrega os modelos disponíveis e envia aos dispositivos (comando manual de debug e teste)
- *request*: Solicita o envio de modelos dos dispositivos conectados (comando manual de debug e teste)
- *listen*: Inicia um servidor que apenas escuta e salva mensagens recebidas (comando de debug e teste)


## 📁 Estrutura de Armazenamento

### Pasta weights
Armazena os modelos recebidos dos dispositivos e os pesos agregados:

- `[cliente].json`: Modelos recebidos de dispositivos individuais
- `aggregated_weights.json`: Modelo agregado após cada rodada

Durante um processo federativo, uma pasta com timestamp é criada (ex: 2023-05-08_15-30-00/), contendo subpastas numeradas para cada rodada.

### Pasta parse
Local onde arquivos JSON de métricas são colocados para análise. O formato esperado inclui:

- Métricas de desempenho (accuracy, precision, recall, etc)
- Informações de temporização do treinamento
- Detalhes do dataset e configuração do modelo

### Pasta metrics
Destino dos gráficos gerados pela função parse, incluindo:

- `plot_average_[metrica].png`: Evolução da média de métricas por rodada
- `heatmap_[metrica].png`: Mapa de calor comparando dispositivos
- `model_architecture_[arquitetura].png`: Visualização da rede neural
- outros arquivos e métricas estão disponíveis

## 📝 Notas de Uso
- O broker MQTT deve estar em execução antes de iniciar o servidor
- Para aprendizado federado completo, os dispositivos devem estar conectados antes de iniciar
- Recomenda-se verificar as configurações do broker MQTT para evitar desconexões por timeout
- Para análises dos dados, utilize a opção `parse` após finalizar um ciclo de aprendizado federado, depois de copiar o resultado do processo federado da pasta `weights` até a pasta `parse`