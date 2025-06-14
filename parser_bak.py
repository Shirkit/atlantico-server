import os
import json
import re
from collections import defaultdict
import matplotlib.pyplot as plt
import traceback
import numpy as np
import seaborn as sns

def do_parse(parse_folder, metrics_folder):
    found_files = [] 
    for root, dirs, files in os.walk(parse_folder):
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
                data["timings"] = data["data"]["timings"]
                data["datasetSize"] = data["data"]["datasetSize"]
                data["model"] = data["data"]["model"]
                data["epochs"] = data["data"]["epochs"]
                data["memory"] = data["data"]["memory"]
                data["data"] = None
                json_data.append(data)
                print(data)
            except json.JSONDecodeError as e:
                print(f"Error parsing {file}: {e}")

    print("Dados parseados com sucesso.")

    # List of metrics to plot - add or remove as needed
    metrics_to_plot = ["meanSqrdError", "accuracy", "precision", "recall", "f1Score"]

    plot_average_metrics(json_data, metrics_folder, metrics_to_plot)
    
    for metric in metrics_to_plot:
        try:
            plot_metrics(json_data, metrics_folder, metric)
            plot_clients_heatmap(json_data, metrics_folder, metric)
        except Exception as e:
            print(f"Error plotting {metric}: {e}")
    
    # Plot multiple metrics for all clients
    for client_id in set(item["client"] for item in json_data):
        try:
            plot_multiple_metrics(json_data, client_id, metrics_folder, metrics=metrics_to_plot)
        except Exception as e:
            print(f"Error plotting metrics for client {client_id}: {e}")

    try:
        plot_training_efficiency(json_data, metrics_folder)
        plot_processing_time_breakdown(json_data, metrics_folder)
        plot_training_efficiency_per_epoch(json_data, metrics_folder)
        plot_model_architecture(json_data, metrics_folder)
        plot_training_speed_vs_complexity(json_data, metrics_folder)
        plot_combined_processing_time_breakdown(json_data, metrics_folder)
        plot_fixed_memory_metrics(json_data, metrics_folder)
        plot_round_memory_metrics(json_data, metrics_folder)
    except Exception as e:
        print(f"Error generating performance plots: {e}")
        print(traceback.format_exc())

def plot_metrics(json_data, metrics_folder, metric_name="meanSqrdError"):
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
    plt.savefig(metrics_folder + filename)
    print(f"Plot saved as {filename}")
    plt.close()
    
    # Show plot
    # plt.show()

def plot_multiple_metrics(json_data, client_id, metrics_folder, metrics=["meanSqrdError", "accuracy"]):
    """Plot multiple metrics for a specific client"""
    
    # Filter data for specific client
    client_data = [item for item in json_data if item["client"] == client_id]
    
    if not client_data:
        print(f"No data found for client: {client_id}")
        return
    
    # Sort by round
    client_data.sort(key=lambda x: x.get("round", 0))
    
    plt.figure(figsize=(12, 8))
    
    for metric in metrics:
        values = []
        rounds = []
        for item in client_data:
            if metric in item["metrics"]:
                values.append(float(item["metrics"][metric]))
                rounds.append(item.get("round", 0))
        
        if values:
            plt.plot(rounds, values, 'o-', label=metric)
    
    plt.title(f"Metrics Evolution for Client {client_id}")
    plt.xlabel("Round")
    plt.ylabel("Metric Value")
    plt.legend()
    plt.grid(True)
    
    filename = f"plot_client_{client_id}_metrics.png"
    plt.savefig(metrics_folder + filename)
    plt.close()
    # plt.show()

def plot_clients_heatmap(json_data, metrics_folder, metric="meanSqrdError"):
    """Create a heatmap showing all clients' performance across rounds"""
    
    # Get unique clients and rounds
    clients = set()
    rounds = set()
    
    for item in json_data:
        clients.add(item["client"])
        rounds.add(item.get("round", 0))
    
    clients = sorted(list(clients))
    rounds = sorted(list(rounds))
    
    # Create matrix for heatmap
    matrix = np.zeros((len(clients), len(rounds)))
    matrix[:] = np.nan  # Fill with NaN initially
    
    # Fill matrix with data
    for item in json_data:
        client = item["client"]
        round_num = item.get("round", 0)
        
        if metric in item["metrics"]:
            client_idx = clients.index(client)
            round_idx = rounds.index(round_num)
            matrix[client_idx][round_idx] = float(item["metrics"][metric])
    
    # Create heatmap
    plt.figure(figsize=(12, 8))
    sns.heatmap(matrix, annot=True, fmt=".3f", cmap="viridis", 
                xticklabels=rounds, yticklabels=clients)
    plt.title(f"Heatmap of {metric} across clients and rounds")
    plt.xlabel("Round")
    plt.ylabel("Client")
    
    plt.savefig(metrics_folder + f"heatmap_{metric}.png")
    plt.close()
    # plt.show()

def plot_training_efficiency_per_epoch(json_data, metrics_folder):
    """Plot relationship between training time per sample and accuracy"""
    
    # Extract data
    times_per_sample = []
    accuracies = []
    client_rounds = []
    epochs_list = []
    
    for item in json_data:
        if "timings" in item and "training" in item["timings"]:
            training_time = item["timings"]["training"] / 1000  # seconds
            dataset_size = item["datasetSize"]
            if not dataset_size:
                continue  # Skip if dataset size is zero
            epochs = item["epochs"]
            
            # Calculate time per sample per epoch
            time_per_sample = training_time / (dataset_size * epochs)
            
            times_per_sample.append(time_per_sample)
            accuracies.append(float(item["metrics"]["accuracy"]))
            client_rounds.append(f"{item['client']}-R{item.get('round', 0)}")
            epochs_list.append(epochs)
    
    # Create plot
    plt.figure(figsize=(12, 8))
    
    # Create scatter plot with size based on epochs
    scatter = plt.scatter(times_per_sample, accuracies, 
                        c=epochs_list, s=80, alpha=0.7, 
                        cmap='plasma', marker='o')
    
    # Add labels
    for i, cr in enumerate(client_rounds):
        plt.annotate(cr, (times_per_sample[i], accuracies[i]), 
                    textcoords="offset points", xytext=(5,5))
    
    # Add trend line
    z = np.polyfit(times_per_sample, accuracies, 1)
    p = np.poly1d(z)
    plt.plot([min(times_per_sample), max(times_per_sample)], 
            [p(min(times_per_sample)), p(max(times_per_sample))], 
            "r--", alpha=0.8)
    
    cbar = plt.colorbar(scatter)
    cbar.set_label('Number of Epochs')
    
    plt.title('Training Efficiency: Accuracy vs Time per Sample per Epoch')
    plt.xlabel('Time per Sample per Epoch (seconds)')
    plt.ylabel('Accuracy')
    plt.grid(True, linestyle='--', alpha=0.7)
    
    plt.tight_layout()
    plt.savefig(metrics_folder + "training_efficiency_per_epoch.png")
    plt.close()
    # plt.show()

def plot_model_architecture(json_data, metrics_folder):
    """Visualize the neural network architecture used in the training"""
    
    # Find unique model architectures
    model_architectures = {}
    
    for item in json_data:
        if "model" in item:
            arch_key = "-".join(str(x) for x in item["model"])
            if arch_key not in model_architectures:
                model_architectures[arch_key] = {
                    "architecture": item["model"],
                    "clients": []
                }
            if item["client"] not in model_architectures[arch_key]["clients"]:
                model_architectures[arch_key]["clients"].append(item["client"])
    
    # Plot each unique architecture
    for arch_key, arch_data in model_architectures.items():
        layers = arch_data["architecture"]
        clients = arch_data["clients"]
        
        plt.figure(figsize=(10, 6))
        
        # Plot layers as circles with size proportional to nodes
        x = np.arange(len(layers))
        y = np.zeros(len(layers))
        
        max_nodes = max(layers)
        sizes = [1000 * layer / max_nodes for layer in layers]
        
        plt.scatter(x, y, s=sizes, c=range(len(layers)), cmap='coolwarm', alpha=0.7, zorder=2)
        
        # Draw connections between layers
        for i in range(len(layers) - 1):
            plt.plot([i, i+1], [0, 0], 'gray', alpha=0.5, zorder=1)
        
        # Add layer labels with node counts
        for i, layer_size in enumerate(layers):
            plt.annotate(f"{layer_size}", (i, 0), textcoords="offset points", 
                    xytext=(0,10), ha='center', fontsize=12, fontweight='bold')
        
        plt.title(f'Neural Network Architecture: {arch_key}')
        plt.xlabel('Layer')
        plt.xticks(x, [f'Layer {i}' for i in range(len(layers))])
        plt.yticks([])
        plt.grid(False)
        
        # Add client info
        plt.figtext(0.5, 0.01, f"Used by clients: {', '.join(clients)}", 
                ha="center", fontsize=10)
        
        plt.tight_layout()
        plt.savefig(metrics_folder + f"model_architecture_{arch_key}.png")
        plt.close()
        # plt.show()

def plot_training_speed_vs_complexity(json_data, metrics_folder):
    """Plot the relationship between model complexity and training speed"""
    
    # Extract data
    model_sizes = []  # Total number of weights/parameters
    training_speeds = []  # Samples per second
    client_rounds = []
    f1_scores = []
    
    for item in json_data:
        if "model" in item and "timings" in item:
            # Calculate model size (total parameters)
            layers = item["model"]
            params = 0
            for i in range(len(layers)-1):
                params += layers[i] * layers[i+1]  # Weights
                params += layers[i+1]  # Biases
            
            # Calculate training speed
            training_time = item["timings"].get("training", 0) / 1000  # seconds
            if training_time > 0:
                samples_per_second = item["datasetSize"] / training_time
            else:
                samples_per_second = 0
            
            model_sizes.append(params)
            training_speeds.append(samples_per_second)
            client_rounds.append(f"{item['client']}-R{item.get('round', 0)}")
            f1_scores.append(float(item["metrics"]["f1Score"]))
    
    # Create plot
    plt.figure(figsize=(12, 8))
    
    scatter = plt.scatter(model_sizes, training_speeds, 
                        c=f1_scores, s=100, alpha=0.7, 
                        cmap='YlGnBu')
    
    # Add annotations
    for i, cr in enumerate(client_rounds):
        plt.annotate(cr, (model_sizes[i], training_speeds[i]), 
                    textcoords="offset points", xytext=(5,5))
    
    # Add trend line
    if len(model_sizes) > 1:
        z = np.polyfit(model_sizes, training_speeds, 1)
        p = np.poly1d(z)
        plt.plot([min(model_sizes), max(model_sizes)], 
                [p(min(model_sizes)), p(max(model_sizes))], 
                "r--", alpha=0.8)
    
    cbar = plt.colorbar(scatter)
    cbar.set_label('F1 Score')
    
    plt.title('Training Speed vs Model Complexity')
    plt.xlabel('Model Size (number of parameters)')
    plt.ylabel('Training Speed (samples/second)')
    plt.grid(True, linestyle='--', alpha=0.7)
    
    plt.tight_layout()
    plt.savefig(metrics_folder + "training_speed_vs_complexity.png")
    plt.close()
    # plt.show()

def plot_combined_processing_time_breakdown(json_data, metrics_folder):
    """
    Plot combined time breakdown for all clients in a single graph,
    allowing comparison between clients across rounds.
    
    Parameters:
    - json_data: List of parsed JSON objects with timing data
    """
    # Extract all clients and rounds for organizing the plot
    clients = sorted(set(item["client"] for item in json_data))
    rounds = sorted(set(item.get("round", 0) for item in json_data))
    
    if not clients or not rounds:
        print("No client or round data found for combined processing time plot")
        return
        
    # Prepare data structures to hold timing information
    training_data = np.zeros((len(clients), len(rounds)))
    parsing_data = np.zeros((len(clients), len(rounds)))
    construct_data = np.zeros((len(clients), len(rounds)))
    
    # Fill with NaN initially to handle missing data points
    training_data[:] = np.nan
    parsing_data[:] = np.nan
    construct_data[:] = np.nan
    
    # Collect timing data for each client and round
    for item in json_data:
        if "timings" not in item:
            continue
            
        client = item["client"]
        round_num = item.get("round", 0)
        
        client_idx = clients.index(client)
        round_idx = rounds.index(round_num)
        
        timings = item["timings"]
        
        # Convert milliseconds to seconds
        if "training" in timings:
            training_data[client_idx, round_idx] = timings["training"] / 1000
        if "parsing" in timings:
            parsing_data[client_idx, round_idx] = timings["parsing"] / 1000
        if "previousConstruct" in timings:
            construct_data[client_idx, round_idx] = timings["previousConstruct"] / 1000
    
    # Color map for different clients
    colors = plt.cm.tab10(np.linspace(0, 1, len(clients)))
    
    # Create four separate plots
    
    # 1. Training time plot
    fig_training, ax_training = plt.subplots(figsize=(12, 6))
    for i, client in enumerate(clients):
        ax_training.plot(rounds, training_data[i], 'o-', linewidth=2, 
                label=f"Cliente {client}", color=colors[i])
    ax_training.set_title('Tempo de Treinamento por Round', fontsize=14)
    ax_training.set_ylabel('Tempo (segundos)')
    ax_training.set_xlabel('Round')
    ax_training.grid(True, linestyle='--', alpha=0.7)
    ax_training.legend(loc='upper left')
    ax_training.set_xticks(rounds)
    ax_training.set_xticklabels([f'Round {r}' for r in rounds])
    plt.tight_layout()
    plt.savefig(metrics_folder + "combined_training_time.png")
    print("Plot saved as combined_training_time.png")
    plt.close(fig_training)
    
    # 2. Parsing time plot
    fig_parsing, ax_parsing = plt.subplots(figsize=(12, 6))
    for i, client in enumerate(clients):
        ax_parsing.plot(rounds, parsing_data[i], 'o-', linewidth=2, 
                label=f"Cliente {client}", color=colors[i])
    ax_parsing.set_title('Tempo de Parsing por Round', fontsize=14)
    ax_parsing.set_ylabel('Tempo (segundos)')
    ax_parsing.set_xlabel('Round')
    ax_parsing.grid(True, linestyle='--', alpha=0.7)
    ax_parsing.legend(loc='upper left')
    ax_parsing.set_xticks(rounds)
    ax_parsing.set_xticklabels([f'Round {r}' for r in rounds])
    plt.tight_layout()
    plt.savefig(metrics_folder + "combined_parsing_time.png")
    print("Plot saved as combined_parsing_time.png")
    plt.close(fig_parsing)
    
    # 3. Construction time plot
    fig_construct, ax_construct = plt.subplots(figsize=(12, 6))
    for i, client in enumerate(clients):
        ax_construct.plot(rounds, construct_data[i], 'o-', linewidth=2, 
                label=f"Cliente {client}", color=colors[i])
    ax_construct.set_title('Tempo de Construção do Modelo por Round', fontsize=14)
    ax_construct.set_xlabel('Round')
    ax_construct.set_ylabel('Tempo (segundos)')
    ax_construct.grid(True, linestyle='--', alpha=0.7)
    ax_construct.legend(loc='upper left')
    ax_construct.set_xticks(rounds)
    ax_construct.set_xticklabels([f'Round {r}' for r in rounds])
    plt.tight_layout()
    plt.savefig(metrics_folder + "combined_construction_time.png")
    print("Plot saved as combined_construction_time.png")
    plt.close(fig_construct)
    
    # 4. Total time stacked bar chart
    fig_total, ax_total = plt.subplots(figsize=(14, 8))
    
    # Calculate positions for grouped bars
    bar_width = 0.8 / len(clients)
    client_positions = {}
    
    # Create grouped stacked bars
    for i, client in enumerate(clients):
        bottom = np.zeros(len(rounds))
        positions = np.arange(len(rounds)) - 0.4 + (i + 0.5) * bar_width
        client_positions[client] = positions
        
        # Training time (bottom part)
        training_vals = np.nan_to_num(training_data[i], nan=0)
        ax_total.bar(positions, training_vals, bar_width, bottom=bottom,
                    label=f'Treinamento ({client})' if i == 0 else "", 
                    color='#3274A1', alpha=0.7)
        bottom += training_vals
        
        # Parsing time (middle part)
        parsing_vals = np.nan_to_num(parsing_data[i], nan=0)
        ax_total.bar(positions, parsing_vals, bar_width, bottom=bottom,
                    label=f'Parsing ({client})' if i == 0 else "", 
                    color='#E1812C', alpha=0.7)
        bottom += parsing_vals
        
        # Construct time (top part)
        construct_vals = np.nan_to_num(construct_data[i], nan=0)
        ax_total.bar(positions, construct_vals, bar_width, bottom=bottom,
                    label=f'Construção ({client})' if i == 0 else "", 
                    color='#3A923A', alpha=0.7)
    
    # Add client labels
    # for i, client in enumerate(clients):
    #     positions = client_positions[client]
    #     # Add client label in the middle of their group
    #     if len(rounds) > 0:
    #         ax_total.text(np.mean(positions), -2, f"Cliente {client}", 
    #                      ha='center', va='top', fontsize=10, 
    #                      color=colors[i], fontweight='bold')
    
    ax_total.set_title('Tempo Total de Processamento por Cliente e Round', fontsize=14)
    ax_total.set_xlabel('Round')
    ax_total.set_ylabel('Tempo Total (segundos)')
    ax_total.set_xticks(np.arange(len(rounds)))
    ax_total.set_xticklabels([f'Round {r}' for r in rounds])
    ax_total.grid(True, axis='y', linestyle='--', alpha=0.7)
    
    # Create a custom legend for client colors
    # client_handles = [plt.Line2D([0], [0], color=colors[i], lw=4, label=f'Cliente {client}') 
    #                  for i, client in enumerate(clients)]
    
    # Add a legend with both phase and client information
    phase_handles = [plt.Rectangle((0,0), 1, 1, color=c, alpha=0.7) 
                    for c in ['#3274A1', '#E1812C', '#3A923A']]
    phase_labels = ['Treinamento', 'Parsing', 'Construção']
    
    # Position both legends properly
    # legend1 = ax_total.legend(handles=client_handles, title="Clientes", 
    #                          loc='upper right', bbox_to_anchor=(1.15, 1))
    # ax_total.add_artist(legend1)
    
    # Second legend for phases
    legend2 = ax_total.legend(handles=phase_handles, labels=phase_labels, 
                            title="Fases", loc='upper right',
                            bbox_to_anchor=(1.15, 0.7))
    ax_total.add_artist(legend2)
    
    # Adjust layout
    plt.tight_layout()
    fig_total.subplots_adjust(right=0.85)
    
    # Save the plot
    plt.savefig(metrics_folder + "combined_total_time.png")
    print("Plot saved as combined_total_time.png")
    
    plt.close(fig_total)

def plot_processing_time_breakdown(json_data, metrics_folder):
    """Plot time breakdown for different processing stages"""
    
    # Create structure to hold timing data by client
    clients = {}
    
    for item in json_data:
        client = item["client"]
        timings = item["timings"]
        round_num = item.get("round", 0)
        
        if client not in clients:
            clients[client] = {"rounds": [], "training": [], "parsing": [], "construct": []}
        
        clients[client]["rounds"].append(round_num)
        clients[client]["training"].append(timings.get("training", 0) / 1000)  # Convert to seconds
        clients[client]["parsing"].append(timings.get("parsing", 0) / 1000)
        clients[client]["construct"].append(timings.get("previousConstruct", 0) / 1000)
    
    # Plot timing breakdown for each client
    for client, data in clients.items():
        # Sort by round
        rounds = np.array(data["rounds"])
        sort_idx = np.argsort(rounds)
        rounds = rounds[sort_idx]
        training = np.array(data["training"])[sort_idx]
        parsing = np.array(data["parsing"])[sort_idx]
        construct = np.array(data["construct"])[sort_idx]
        
        plt.figure(figsize=(10, 6))
        
        width = 0.25
        x = np.arange(len(rounds))
        
        plt.bar(x - width, training, width, label='Training')
        plt.bar(x, parsing, width, label='Parsing')
        plt.bar(x + width, construct, width, label='Model Construction')
        
        plt.title(f'Processing Time Breakdown for Client {client}')
        plt.xlabel('Round')
        plt.ylabel('Time (seconds)')
        plt.xticks(x, [str(r) for r in rounds])
        plt.legend()
        plt.grid(True, axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        plt.savefig(metrics_folder + f"time_breakdown_client_{client}.png")
        plt.close()
        # plt.show()

def plot_training_efficiency(json_data, metrics_folder):
    """Plot the relationship between training time, dataset size, and model performance"""
    
    # Extract relevant data
    training_times = []
    dataset_sizes = []
    errors = []
    accuracies = []
    client_ids = []
    epochs = []
    
    for item in json_data:
        if "timings" in item and "training" in item["timings"]:
            training_times.append(item["timings"]["training"] / 1000)  # Convert to seconds
            dataset_sizes.append(item["datasetSize"])
            errors.append(float(item["metrics"]["meanSqrdError"]))
            accuracies.append(float(item["metrics"]["accuracy"]))
            client_ids.append(item["client"])
            epochs.append(item["epochs"])
    
    # Create scatter plot
    plt.figure(figsize=(12, 8))
    scatter = plt.scatter(dataset_sizes, training_times, 
                        c=accuracies, s=np.array(epochs)*50, 
                        alpha=0.7, cmap='viridis')
    
    # Add labels for each point
    for i, client in enumerate(client_ids):
        plt.annotate(client, (dataset_sizes[i], training_times[i]), 
                    textcoords="offset points", xytext=(0,10), ha='center')
    
    # Add colorbar for accuracy
    cbar = plt.colorbar(scatter)
    cbar.set_label('Accuracy')
    
    # Create legend for epochs
    unique_epochs = sorted(set(epochs))
    handles = [plt.scatter([], [], s=e*50, color='gray', alpha=0.7) for e in unique_epochs]
    plt.legend(handles, [f'{e} epoch(s)' for e in unique_epochs], title="Training Epochs",
            loc="upper left")
    
    plt.title('Training Time vs Dataset Size')
    plt.xlabel('Dataset Size (samples)')
    plt.ylabel('Training Time (seconds)')
    plt.grid(True, linestyle='--', alpha=0.7)
    
    plt.tight_layout()
    plt.savefig(metrics_folder + "training_efficiency.png")
    plt.close()
    # plt.show()

def plot_average_metrics(json_data, metrics_folder, metrics_to_plot=["meanSqrdError", "accuracy", "precision", "recall", "f1Score"]):
    """
    Plot the average value of each metric across all clients for each round.
    
    Parameters:
    - json_data: List of parsed JSON objects with metrics
    - metrics_to_plot: List of metrics to include in the plot
    """
    # Group data by round and metric
    round_data = defaultdict(lambda: defaultdict(list))
    
    # Get all rounds
    all_rounds = sorted(set(item.get("round", 0) for item in json_data))
    
    # Extract metrics by round
    for item in json_data:
        round_num = item.get("round", 0)
        for metric in metrics_to_plot:
            if metric in item["metrics"]:
                try:
                    value = float(item["metrics"][metric])
                    round_data[round_num][metric].append(value)
                except (ValueError, TypeError):
                    # Skip non-numeric values
                    pass
    
    # Calculate averages
    averages = {}
    for metric in metrics_to_plot:
        averages[metric] = []
        for round_num in all_rounds:
            values = round_data[round_num][metric]
            if values:
                avg = sum(values) / len(values)
                averages[metric].append((round_num, avg))
            else:
                # No data for this round and metric
                pass
    
    # Create plot
    plt.figure(figsize=(12, 8))
    
    for metric, points in averages.items():
        if points:  # Only plot if we have data
            # Sort by round number
            points.sort(key=lambda x: x[0])
            rounds = [p[0] for p in points]
            values = [p[1] for p in points]
            plt.plot(rounds, values, 'o-', linewidth=2, label=metric)
    
    plt.title("Average Metrics Across All Clients by Round")
    plt.xlabel("Round")
    plt.ylabel("Average Metric Value")
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xticks(all_rounds)  # Show all rounds on x-axis
    
    # Add value annotations to points
    for metric, points in averages.items():
        if points:
            for round_num, value in points:
                plt.annotate(f"{value:.3f}", 
                            (round_num, value),
                            textcoords="offset points", 
                            xytext=(0,10), 
                            ha='center')
    
    # Save plot
    filename = "plot_average_metrics.png"
    plt.savefig(metrics_folder + filename)
    print(f"Plot saved as {filename}")
    plt.close()
    
    # Show plot
    # plt.show()

    # Also create individual plots for each metric for clarity
    for metric in metrics_to_plot:
        if metric not in averages or not averages[metric]:
            continue
            
        plt.figure(figsize=(10, 6))
        points = sorted(averages[metric], key=lambda x: x[0])
        rounds = [p[0] for p in points]
        values = [p[1] for p in points]
        
        plt.plot(rounds, values, 'o-', linewidth=3, color='blue')
        plt.title(f"Average {metric} Across All Clients by Round")
        plt.xlabel("Round")
        plt.ylabel(f"Average {metric}")
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.xticks(all_rounds)
        
        # Add value annotations
        for round_num, value in zip(rounds, values):
            plt.annotate(f"{value:.3f}", 
                        (round_num, value),
                        textcoords="offset points", 
                        xytext=(0,10), 
                        ha='center')
        
        filename = f"plot_average_{metric}.png"
        plt.savefig(metrics_folder + filename)
        print(f"Plot saved as {filename}")
        plt.close()
        # plt.show()

def plot_fixed_memory_metrics(json_data, metrics_folder):
    """
    Plot fixed memory metrics as a single bar chart showing average values across all devices.
    These are boot-time memory measurements that remain constant per device.
    Units displayed in KB.
    """
    # Extract fixed memory metrics
    fixed_metrics = {}
    clients = set()
    
    for item in json_data:
        if "memory" in item and "fixed" in item["memory"]:
            client = item["client"]
            clients.add(client)
            
            for metric_name, value in item["memory"]["fixed"].items():
                if metric_name not in fixed_metrics:
                    fixed_metrics[metric_name] = []
                
                # Convert bytes to KB safely
                if value is not None and value > 0:
                    kb_value = value / 1024
                else:
                    kb_value = 0.0
                
                fixed_metrics[metric_name].append(kb_value)
    
    if not fixed_metrics:
        print("No fixed memory metrics found")
        return
    
    # Calculate average for each metric across all clients and rounds
    metric_names = []
    metric_averages = []
    
    for metric_name, values in fixed_metrics.items():
        # Filter out zero values for average calculation if there are non-zero values
        non_zero_values = [v for v in values if v > 0]
        if non_zero_values:
            avg_value = sum(non_zero_values) / len(non_zero_values)
        else:
            # If all values are zero, keep it as zero
            avg_value = 0.0
        
        metric_names.append(metric_name.replace("_", " ").title())
        metric_averages.append(avg_value)
    
    # Create single bar chart
    plt.figure(figsize=(14, 8))
    
    # Use different colors for each bar
    colors = plt.cm.Set3(np.linspace(0, 1, len(metric_names)))
    
    bars = plt.bar(metric_names, metric_averages, color=colors, alpha=0.8, edgecolor='black', linewidth=1)
    
    # Add value labels on top of bars
    for bar, value in zip(bars, metric_averages):
        height = bar.get_height()
        if height > 0:
            plt.text(bar.get_x() + bar.get_width()/2., height + max(metric_averages) * 0.01,
                    f'{value:.1f} KB', ha='center', va='bottom', fontsize=11, fontweight='bold')
        else:
            plt.text(bar.get_x() + bar.get_width()/2., max(metric_averages) * 0.02,
                    'N/A', ha='center', va='bottom', fontsize=11, color='red', fontweight='bold')
    
    # Customize the plot
    plt.title('Average Fixed Memory Metrics Across All Devices', fontsize=16, fontweight='bold', pad=20)
    plt.ylabel('Memory (KB)', fontsize=14)
    plt.xlabel('Memory Metrics', fontsize=14)
    
    # Add grid for better readability
    plt.grid(True, axis='y', linestyle='--', alpha=0.7)
    
    # Set y-axis to start from 0 and add some padding at the top
    if max(metric_averages) > 0:
        plt.ylim(bottom=0, top=max(metric_averages) * 1.15)
    else:
        plt.ylim(bottom=0, top=100)  # Default range if all values are 0
    
    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45, ha='right')
    
    # Add some statistics as text
    total_clients = len(clients)
    total_measurements = sum(len(values) for values in fixed_metrics.values())
    
    plt.figtext(0.02, 0.02, f'Based on {total_measurements} measurements from {total_clients} clients', 
            fontsize=10, style='italic', alpha=0.7)
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.15)
    
    # Save the plot
    plt.savefig(metrics_folder + "fixed_memory_metrics.png", dpi=300, bbox_inches='tight')
    print("Plot saved as fixed_memory_metrics.png")
    plt.close()

def plot_round_memory_metrics(json_data, metrics_folder):
    """
    Plot round-based memory metrics as a single line chart showing average evolution across federation rounds.
    Each line represents the average of all devices for one metric.
    Units displayed in KB.
    """
    # Extract round memory metrics
    round_metrics = {}
    rounds = set()
    
    for item in json_data:
        if "memory" in item and "round" in item["memory"]:
            round_num = item.get("round", 0)
            rounds.add(round_num)
            
            for metric_name, value in item["memory"]["round"].items():
                if metric_name not in round_metrics:
                    round_metrics[metric_name] = {}
                
                if round_num not in round_metrics[metric_name]:
                    round_metrics[metric_name][round_num] = []
                
                # Convert bytes to KB safely
                if value is not None and value > 0:
                    kb_value = value / 1024
                else:
                    kb_value = 0.0
                
                round_metrics[metric_name][round_num].append(kb_value)
    
    if not round_metrics:
        print("No round memory metrics found")
        return
    
    rounds_list = sorted(list(rounds))
    
    # Calculate averages for each metric per round
    metric_averages = {}
    for metric_name, round_data in round_metrics.items():
        metric_averages[metric_name] = []
        
        for round_num in rounds_list:
            if round_num in round_data:
                values = round_data[round_num]
                # Filter out zero values for average calculation if there are non-zero values
                non_zero_values = [v for v in values if v > 0]
                if non_zero_values:
                    avg_value = sum(non_zero_values) / len(non_zero_values)
                else:
                    # If all values are zero, keep it as zero
                    avg_value = 0.0
            else:
                avg_value = 0.0
            
            metric_averages[metric_name].append(avg_value)
    
    # Create single line chart
    plt.figure(figsize=(14, 8))
    
    # Use different colors and line styles for each metric
    colors = plt.cm.tab10(np.linspace(0, 1, len(metric_averages)))
    line_styles = ['-', '--', '-.', ':', '-', '--']  # Cycle through different line styles
    markers = ['o', 's', '^', 'D', 'v', 'p']  # Different markers for each line
    
    # Plot each metric
    for idx, (metric_name, averages) in enumerate(metric_averages.items()):
        color = colors[idx % len(colors)]
        line_style = line_styles[idx % len(line_styles)]
        marker = markers[idx % len(markers)]
        
        label = metric_name.replace("_", " ").title()
        
        plt.plot(rounds_list, averages, 
                color=color, 
                linestyle=line_style, 
                marker=marker, 
                linewidth=2.5, 
                markersize=8, 
                label=label,
                alpha=0.8)
        
        # Add value annotations for each point
        # for round_num, avg_value in zip(rounds_list, averages):
        #     if avg_value > 0:  # Only annotate non-zero values
        #         plt.annotate(f'{avg_value:.1f}', 
        #                    (round_num, avg_value), 
        #                    textcoords="offset points", 
        #                    xytext=(0, 15), 
        #                    ha='center', 
        #                    fontsize=9, 
        #                    color=color,
        #                    alpha=0.8)
    
    # Customize the plot
    plt.title('Average Round Memory Metrics Evolution Across Federation Rounds', 
            fontsize=16, fontweight='bold', pad=20)
    plt.ylabel('Memory (KB)', fontsize=14)
    plt.xlabel('Round', fontsize=14)
    
    # Add grid for better readability
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Customize x-axis
    plt.xticks(rounds_list, [f'Round {r}' for r in rounds_list])
    
    # Set y-axis to start from 0
    all_values = [val for averages in metric_averages.values() for val in averages if val > 0]
    if all_values:
        plt.ylim(bottom=0, top=max(all_values) * 1.2)
    else:
        plt.ylim(bottom=0, top=100)  # Default range if all values are 0
    
    # Add legend
    plt.legend(loc='best', frameon=True, fancybox=True, shadow=True, fontsize=11)
    
    # Add some statistics as text
    total_metrics = len(round_metrics)
    total_rounds = len(rounds_list)
    
    plt.figtext(0.02, 0.02, 
            f'Showing averages across all devices for {total_metrics} metrics over {total_rounds} rounds', 
            fontsize=10, style='italic', alpha=0.7)
    
    # Add special annotation for Round 0 if it exists and has zero values
    if 0 in rounds_list:
        zero_metrics = []
        for metric_name, averages in metric_averages.items():
            if averages[rounds_list.index(0)] == 0:
                zero_metrics.append(metric_name)
        
        if zero_metrics:
            plt.figtext(0.02, 0.95, 
                    f'Round 0 note: {len(zero_metrics)} metrics show zero values (initialization)', 
                    fontsize=10, 
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7),
                    transform=plt.gca().transAxes)
    
    # Adjust layout
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.12)
    
    # Save the plot
    plt.savefig(metrics_folder + "round_memory_metrics.png", dpi=300, bbox_inches='tight')
    print("Plot saved as round_memory_metrics.png")
    plt.close()
