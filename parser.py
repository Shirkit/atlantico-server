import os
import json
import re
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for script execution
import matplotlib.pyplot as plt
import traceback
import numpy as np
import seaborn as sns

# Set matplotlib performance optimizations
plt.rcParams['figure.max_open_warning'] = 0
plt.ioff()  # Turn off interactive mode

# STANDARDIZED FIGURE SIZES
STANDARD_FIGURE_SIZE = (12, 8)  # Width x Height in inches
SMALL_FIGURE_SIZE = (10, 6)     # For simpler plots
LARGE_FIGURE_SIZE = (14, 10)    # For complex plots with lots of data

# Standard DPI for consistent quality
STANDARD_DPI = 150

# STANDARDIZED FONT CONFIGURATIONS
TITLE_FONTSIZE = 16
TITLE_FONTWEIGHT = 'bold'
TITLE_PAD = 20

AXIS_LABEL_FONTSIZE = 14
TICK_LABEL_FONTSIZE = 12
LEGEND_FONTSIZE = 12
ANNOTATION_FONTSIZE = 11

# LINE AND MARKER CONFIGURATIONS
STANDARD_LINEWIDTH = 2
STANDARD_MARKERSIZE = 6
ANNOTATION_LINEWIDTH = 3
LARGE_MARKERSIZE = 8

def do_parse(parse_folder, metrics_folder):
    """Main parsing function that processes JSON files and generates all plots."""
    found_files = _find_json_files(parse_folder)
    
    if not found_files:
        print("Nenhum arquivo JSON encontrado na pasta de parse.")
        return

    print(f"Found {len(found_files)} JSON files")

    json_data = _load_json_data(found_files)
    if not json_data:
        print("Nenhum dado válido foi carregado.")
        return

    print("Dados parseados com sucesso.")
    _generate_all_plots(json_data, metrics_folder)


def _find_json_files(parse_folder):
    """Find all JSON files in the parse folder, excluding aggregated weights."""
    found_files = []
    for root, dirs, files in os.walk(parse_folder):
        for file in files:
            if file.endswith('.json') and file != "aggregated_weights.json":
                found_files.append(os.path.join(root, file))
    
    found_files.sort()
    return found_files


def _load_json_data(found_files):
    """Load and process JSON data from files."""
    json_data = []
    
    for file in found_files:
        try:
            with open(file, 'r') as f:
                data = json.load(f)
                
                # Extract round number from file path
                round_match = re.search(r'/(\d+)/', file)
                data["round"] = int(round_match.group(1)) if round_match else 6
                
                # Flatten data structure for easier access
                data["metrics"] = data["data"]["metrics"]
                data["client"] = data["data"]["client"]
                data["timings"] = data["data"]["timings"]
                data["dataset_size"] = data["data"]["datasetSize"]
                data["model"] = data["data"]["model"]
                data["epochs"] = data["data"]["epochs"]
                data["memory"] = data["data"]["memory"]
                data["data"] = None  # Clear original data to save memory
                
                json_data.append(data)
                
        except json.JSONDecodeError as e:
            print(f"Error parsing {file}: {e}")
        except KeyError as e:
            print(f"Missing key in {file}: {e}")
    
    return json_data


def _generate_all_plots(json_data, metrics_folder):
    """Generate all plots with error handling."""
    metrics_to_plot = ["meanSqrdError", "accuracy", "precision", "recall", "f1Score"]
    
    # Generate average metrics plot
    plot_average_metrics(json_data, metrics_folder, metrics_to_plot)
    
    # Generate individual metric plots
    for metric in metrics_to_plot:
        try:
            plot_metrics(json_data, metrics_folder, metric)
            plot_clients_heatmap(json_data, metrics_folder, metric)
        except Exception as e:
            print(f"Error plotting {metric}: {e}")
    
    # Generate per-client plots
    for client_id in set(item["client"] for item in json_data):
        try:
            plot_multiple_metrics(json_data, client_id, metrics_folder, metrics_to_plot)
        except Exception as e:
            print(f"Error plotting metrics for client {client_id}: {e}")

    # Generate performance plots
    performance_plots = [
        plot_training_efficiency,
        plot_processing_time_breakdown,
        plot_training_efficiency_per_epoch,
        plot_model_architecture,
        plot_training_speed_vs_complexity,
        plot_combined_processing_time_breakdown,
        plot_average_timing_metrics,  # Add the new function here
        plot_fixed_memory_metrics,
        plot_round_memory_metrics
    ]
    
    for plot_func in performance_plots:
        try:
            plot_func(json_data, metrics_folder)
        except Exception as e:
            print(f"Error in {plot_func.__name__}: {e}")
            print(traceback.format_exc())


def plot_metrics(json_data, metrics_folder, metric_name="meanSqrdError"):
    """Plot the evolution of a specified metric across clients."""
    client_data = defaultdict(list)
    
    # Extract data for each client
    for item in json_data:
        if metric_name in item["metrics"]:
            try:
                metric_value = float(item["metrics"][metric_name])
                round_num = item.get("round", 0)
                client_data[item["client"]].append((round_num, metric_value))
            except (ValueError, TypeError):
                continue
    
    if not client_data:
        print(f"No data found for metric: {metric_name}")
        return
    
    # Create plot with standardized size
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    
    for client, points in client_data.items():
        points.sort(key=lambda x: x[0])
        rounds, values = zip(*points) if points else ([], [])
        plt.plot(rounds, values, 'o-', label=f"Client {client}", linewidth=STANDARD_LINEWIDTH, markersize=STANDARD_MARKERSIZE)
    
    plt.title(f"Evolution of {metric_name} across rounds", fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel("Round", fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel(metric_name, fontsize=AXIS_LABEL_FONTSIZE)
    plt.legend(fontsize=LEGEND_FONTSIZE, bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, linestyle='--', alpha=0.7)
    
    _save_plot(metrics_folder, f"plot_{metric_name}.png")


def plot_multiple_metrics(json_data, client_id, metrics_folder, metrics):
    """Plot multiple metrics for a specific client."""
    client_data = [item for item in json_data if item["client"] == client_id]
    
    if not client_data:
        print(f"No data found for client: {client_id}")
        return
    
    client_data.sort(key=lambda x: x.get("round", 0))
    
    # Use standardized figure size
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    
    for metric in metrics:
        values, rounds = [], []
        for item in client_data:
            if metric in item["metrics"]:
                try:
                    values.append(float(item["metrics"][metric]))
                    rounds.append(item.get("round", 0))
                except (ValueError, TypeError):
                    continue
        
        if values:
            plt.plot(rounds, values, 'o-', label=metric, linewidth=STANDARD_LINEWIDTH, markersize=STANDARD_MARKERSIZE)
    
    plt.title(f"Metrics Evolution for Client {client_id}", fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel("Round", fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel("Metric Value", fontsize=AXIS_LABEL_FONTSIZE)
    plt.legend(fontsize=LEGEND_FONTSIZE, bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, alpha=0.7)
    
    _save_plot(metrics_folder, f"plot_client_{client_id}_metrics.png")



def plot_clients_heatmap(json_data, metrics_folder, metric="meanSqrdError"):
    """Create a heatmap showing all clients' performance across rounds."""
    clients = sorted(set(item["client"] for item in json_data))
    rounds = sorted(set(item.get("round", 0) for item in json_data))
    
    if not clients or not rounds:
        print(f"Insufficient data for heatmap: {len(clients)} clients, {len(rounds)} rounds")
        return
    
    # Create matrix for heatmap
    matrix = np.full((len(clients), len(rounds)), np.nan)
    
    # Fill matrix with data
    for item in json_data:
        if metric in item["metrics"]:
            try:
                client_idx = clients.index(item["client"])
                round_idx = rounds.index(item.get("round", 0))
                matrix[client_idx][round_idx] = float(item["metrics"][metric])
            except (ValueError, TypeError, IndexError):
                continue
    
    # Use standardized figure size
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    sns.heatmap(matrix, annot=True, fmt=".3f", cmap="viridis", 
                xticklabels=rounds, yticklabels=clients)
    plt.title(f"Heatmap of {metric} across clients and rounds", fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel("Round", fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel("Client", fontsize=AXIS_LABEL_FONTSIZE)
    
    _save_plot(metrics_folder, f"heatmap_{metric}.png")


def plot_training_efficiency_per_epoch(json_data, metrics_folder):
    """Plot relationship between training time per sample and accuracy."""
    times_per_sample, accuracies, client_rounds, epochs_list = [], [], [], []
    
    for item in json_data:
        if not _has_timing_data(item) or item["dataset_size"] <= 0:
            continue
        
        try:
            training_time = item["timings"]["training"] / 1000  # Convert to seconds
            time_per_sample = training_time / (item["dataset_size"] * item["epochs"])
            
            times_per_sample.append(time_per_sample)
            accuracies.append(float(item["metrics"]["accuracy"]))
            client_rounds.append(f"{item['client']}-R{item.get('round', 0)}")
            epochs_list.append(item["epochs"])
        except (ValueError, TypeError, ZeroDivisionError):
            continue
    
    if not times_per_sample:
        print("No valid training efficiency data found")
        return
    
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    
    scatter = plt.scatter(times_per_sample, accuracies, 
                         c=epochs_list, s=80, alpha=0.7, 
                         cmap='plasma', marker='o')
    
    # Add annotations
    for i, label in enumerate(client_rounds):
        plt.annotate(label, (times_per_sample[i], accuracies[i]), 
                    textcoords="offset points", xytext=(5, 5))
    
    # Add trend line
    if len(times_per_sample) > 1:
        z = np.polyfit(times_per_sample, accuracies, 1)
        p = np.poly1d(z)
        x_range = [min(times_per_sample), max(times_per_sample)]
        plt.plot(x_range, [p(x) for x in x_range], "r--", alpha=0.8)
    
    plt.colorbar(scatter, label='Number of Epochs')
    plt.title('Training Efficiency: Accuracy vs Time per Sample per Epoch', fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel('Time per Sample per Epoch (seconds)', fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel('Accuracy', fontsize=AXIS_LABEL_FONTSIZE)
    plt.grid(True, linestyle='--', alpha=0.7)
    
    _save_plot(metrics_folder, "training_efficiency_per_epoch.png")


def plot_model_architecture(json_data, metrics_folder):
    """Visualize the neural network architecture used in the training."""
    model_architectures = {}
    
    # Find unique model architectures
    for item in json_data:
        if "model" not in item:
            continue
        
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
        _plot_single_architecture(arch_data, arch_key, metrics_folder)


def _plot_single_architecture(arch_data, arch_key, metrics_folder):
    """Plot a single neural network architecture."""
    layers = arch_data["architecture"]
    clients = arch_data["clients"]
    
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    
    # Plot layers as circles with size proportional to nodes
    x = np.arange(len(layers))
    y = np.zeros(len(layers))
    
    max_nodes = max(layers) if layers else 1
    sizes = [1000 * layer / max_nodes for layer in layers]
    
    plt.scatter(x, y, s=sizes, c=range(len(layers)), cmap='coolwarm', alpha=0.7, zorder=2)
    
    # Draw connections between layers
    for i in range(len(layers) - 1):
        plt.plot([i, i+1], [0, 0], 'gray', alpha=0.5, zorder=1)
    
    # Add layer labels with node counts
    for i, layer_size in enumerate(layers):
        plt.annotate(f"{layer_size}", (i, 0), textcoords="offset points", 
                    xytext=(0, 10), ha='center', fontsize=12, fontweight='bold')
    
    plt.title(f'Neural Network Architecture: {arch_key}', fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel('Layer', fontsize=AXIS_LABEL_FONTSIZE)
    plt.xticks(x, [f'Layer {i}' for i in range(len(layers))])
    plt.yticks([])
    plt.grid(False)
    
    # Add client info
    plt.figtext(0.5, 0.01, f"Used by clients: {', '.join(clients)}", 
                ha="center", fontsize=10)
    
    _save_plot(metrics_folder, f"model_architecture_{arch_key}.png")


def plot_training_speed_vs_complexity(json_data, metrics_folder):
    """Plot the relationship between model complexity and training speed."""
    model_sizes, training_speeds, client_rounds, f1_scores = [], [], [], []
    
    for item in json_data:
        if not _has_timing_data(item) or "model" not in item:
            continue
        
        try:
            # Calculate model size (total parameters)
            layers = item["model"]
            params = sum(layers[i] * layers[i+1] + layers[i+1] 
                        for i in range(len(layers)-1))
            
            # Calculate training speed
            training_time = item["timings"]["training"] / 1000  # Convert to seconds
            if training_time > 0:
                samples_per_second = item["dataset_size"] / training_time
            else:
                continue
            
            model_sizes.append(params)
            training_speeds.append(samples_per_second)
            client_rounds.append(f"{item['client']}-R{item.get('round', 0)}")
            f1_scores.append(float(item["metrics"]["f1Score"]))
        except (ValueError, TypeError, ZeroDivisionError):
            continue
    
    if not model_sizes:
        print("No valid complexity vs speed data found")
        return
    
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    
    scatter = plt.scatter(model_sizes, training_speeds, 
                         c=f1_scores, s=100, alpha=0.7, cmap='YlGnBu')
    
    # Add annotations
    for i, label in enumerate(client_rounds):
        plt.annotate(label, (model_sizes[i], training_speeds[i]), 
                    textcoords="offset points", xytext=(5, 5))
    
    # Add trend line
    if len(model_sizes) > 1:
        z = np.polyfit(model_sizes, training_speeds, 1)
        p = np.poly1d(z)
        x_range = [min(model_sizes), max(model_sizes)]
        plt.plot(x_range, [p(x) for x in x_range], "r--", alpha=0.8)
    
    plt.colorbar(scatter, label='F1 Score')
    plt.title('Training Speed vs Model Complexity', fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel('Model Size (number of parameters)', fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel('Training Speed (samples/second)', fontsize=AXIS_LABEL_FONTSIZE)
    plt.grid(True, linestyle='--', alpha=0.7)
    
    _save_plot(metrics_folder, "training_speed_vs_complexity.png")


def plot_combined_processing_time_breakdown(json_data, metrics_folder):
    """Plot combined time breakdown for all clients across rounds."""
    clients = sorted(set(item["client"] for item in json_data))
    rounds = sorted(set(item.get("round", 0) for item in json_data))
    
    if not clients or not rounds:
        print("No client or round data found for combined processing time plot")
        return
    
    # Prepare data structures
    time_data = {
        'training': np.full((len(clients), len(rounds)), np.nan),
        'parsing': np.full((len(clients), len(rounds)), np.nan),
        'construct': np.full((len(clients), len(rounds)), np.nan)
    }
    
    # Collect timing data
    for item in json_data:
        if not _has_timing_data(item):
            continue
        
        try:
            client_idx = clients.index(item["client"])
            round_idx = rounds.index(item.get("round", 0))
            
            timings = item["timings"]
            if "training" in timings:
                time_data['training'][client_idx, round_idx] = timings["training"] / 1000
            if "parsing" in timings:
                time_data['parsing'][client_idx, round_idx] = timings["parsing"] / 1000
            if "previousConstruct" in timings:
                time_data['construct'][client_idx, round_idx] = timings["previousConstruct"] / 1000
        except (ValueError, IndexError):
            continue
    
    _plot_time_breakdown_charts(time_data, clients, rounds, metrics_folder)


def _plot_time_breakdown_charts(time_data, clients, rounds, metrics_folder):
    """Create individual time breakdown charts."""
    colors = plt.cm.tab10(np.linspace(0, 1, len(clients)))
    
    # Individual time component plots
    time_types = [
        ('training', 'Tempo de Treinamento por Round'),
        ('parsing', 'Tempo de Parsing por Round'),
        ('construct', 'Tempo de Construção do Modelo por Round')
    ]
    
    for time_type, title in time_types:
        plt.figure(figsize=STANDARD_FIGURE_SIZE)
        
        for i, client in enumerate(clients):
            plt.plot(rounds, time_data[time_type][i], 'o-', linewidth=STANDARD_LINEWIDTH, 
                    label=f"Cliente {client}", color=colors[i])
        
        plt.title(title, fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
        plt.ylabel('Tempo (segundos)', fontsize=AXIS_LABEL_FONTSIZE)
        plt.xlabel('Round', fontsize=AXIS_LABEL_FONTSIZE)
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend(loc='upper left', fontsize=LEGEND_FONTSIZE, bbox_to_anchor=(1.05, 1))
        plt.xticks(rounds, [f'Round {r}' for r in rounds])
        
        _save_plot(metrics_folder, f"combined_{time_type}_time.png")


def plot_average_timing_metrics(json_data, metrics_folder):
    """Plot average timing metrics across all devices for each round."""
    round_timings = defaultdict(lambda: {"training": [], "parsing": [], "construct": []})
    
    # Collect timing data by round
    for item in json_data:
        if not _has_timing_data(item):
            continue
        
        round_num = item.get("round", 0)
        timings = item["timings"]
        
        # Convert from milliseconds to seconds and collect data
        if "training" in timings and timings["training"] is not None:
            round_timings[round_num]["training"].append(timings["training"] / 1000)
        
        if "parsing" in timings and timings["parsing"] is not None:
            round_timings[round_num]["parsing"].append(timings["parsing"] / 1000)
        
        if "previousConstruct" in timings and timings["previousConstruct"] is not None:
            round_timings[round_num]["construct"].append(timings["previousConstruct"] / 1000)
    
    if not round_timings:
        print("No timing data found for average timing metrics")
        return
    
    # Calculate averages for each round
    rounds = sorted(round_timings.keys())
    timing_averages = {
        "training": [],
        "parsing": [],
        "construct": []
    }
    
    for round_num in rounds:
        for timing_type in ["training", "parsing", "construct"]:
            values = round_timings[round_num][timing_type]
            avg_value = sum(values) / len(values) if values else 0.0
            timing_averages[timing_type].append(avg_value)
    
    # Create individual plots for each timing type
    _plot_individual_timing_averages(timing_averages, rounds, metrics_folder)
    
    # Create combined plot
    _plot_combined_timing_averages(json_data, timing_averages, rounds, metrics_folder)


def _plot_individual_timing_averages(timing_averages, rounds, metrics_folder):
    """Create individual plots for each timing metric average."""
    timing_configs = [
        ("training", "Average Training Time Across All Devices", "steelblue", "o"),
        ("parsing", "Average Parsing Time Across All Devices", "darkorange", "s"),
        ("construct", "Average Model Construction Time Across All Devices", "forestgreen", "^")
    ]
    
    for timing_type, title, color, marker in timing_configs:
        values = timing_averages[timing_type]
        
        if not any(v > 0 for v in values):  # Skip if all values are zero
            continue
        
        # Use standardized figure size
        plt.figure(figsize=STANDARD_FIGURE_SIZE)
        
        plt.plot(rounds, values, marker=marker, color=color, linewidth=ANNOTATION_LINEWIDTH, 
                markersize=LARGE_MARKERSIZE, alpha=0.8, markerfacecolor='white', 
                markeredgecolor=color, markeredgewidth=2)
        
        # Add value annotations
        for round_num, value in zip(rounds, values):
            if value > 0:
                plt.annotate(f"{value:.3f}s", (round_num, value),
                           textcoords="offset points", xytext=(0, 15), 
                           ha='center', fontsize=ANNOTATION_FONTSIZE, fontweight='bold')
        
        plt.title(title, fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
        plt.xlabel("Round", fontsize=AXIS_LABEL_FONTSIZE)
        plt.ylabel("Average Time (seconds)", fontsize=AXIS_LABEL_FONTSIZE)
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.xticks(rounds, [f"Round {r}" for r in rounds], fontsize=TICK_LABEL_FONTSIZE)
        plt.yticks(fontsize=TICK_LABEL_FONTSIZE)
        
        # Set y-axis to start from 0
        plt.ylim(bottom=0, top=max(values) * 1.2 if max(values) > 0 else 1)
        
        _save_plot(metrics_folder, f"average_{timing_type}_time.png")


def _plot_combined_timing_averages(json_data, timing_averages, rounds, metrics_folder):
    """Create a combined plot showing all timing averages."""
    # Use standardized figure size
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    
    timing_configs = [
        ("training", "Training Time", "steelblue", "o", "-"),
        ("parsing", "Parsing Time", "darkorange", "s", "--"),
        ("construct", "Model Construction Time", "forestgreen", "^", "-.")
    ]
    
    for timing_type, label, color, marker, linestyle in timing_configs:
        values = timing_averages[timing_type]
        
        if any(v > 0 for v in values):  # Only plot if there are non-zero values
            plt.plot(rounds, values, marker=marker, color=color, linewidth=STANDARD_LINEWIDTH + 0.5,
                    markersize=LARGE_MARKERSIZE, alpha=0.8, label=label, linestyle=linestyle,
                    markerfacecolor='white', markeredgecolor=color, markeredgewidth=2)
    
    plt.title("Average Processing Times Across All Devices by Round", 
             fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel("Round", fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel("Average Time (seconds)", fontsize=AXIS_LABEL_FONTSIZE)
    plt.legend(loc='upper left', frameon=True, fancybox=True, shadow=True, fontsize=LEGEND_FONTSIZE, bbox_to_anchor=(1.05, 1))
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xticks(rounds, [f"Round {r}" for r in rounds], fontsize=TICK_LABEL_FONTSIZE)
    plt.yticks(fontsize=TICK_LABEL_FONTSIZE)
    
    # Set y-axis to start from 0
    all_values = [v for values in timing_averages.values() for v in values if v > 0]
    max_val = max(all_values) if all_values else 1
    plt.ylim(bottom=0, top=max_val * 1.2)
    
    # Add data summary
    device_count = len(set(item["client"] for item in json_data if _has_timing_data(item)))
    plt.figtext(0.02, 0.02, f'Averaged across {device_count} devices', 
                fontsize=10, style='italic', alpha=0.7)
    
    _save_plot(metrics_folder, "average_timing_metrics_combined.png")


def plot_processing_time_breakdown(json_data, metrics_folder):
    """Plot time breakdown for different processing stages by client."""
    clients_data = defaultdict(lambda: {"rounds": [], "training": [], "parsing": [], "construct": []})
    
    for item in json_data:
        if not _has_timing_data(item):
            continue
        
        client = item["client"]
        timings = item["timings"]
        round_num = item.get("round", 0)
        
        clients_data[client]["rounds"].append(round_num)
        clients_data[client]["training"].append(timings.get("training", 0) / 1000)
        clients_data[client]["parsing"].append(timings.get("parsing", 0) / 1000)
        clients_data[client]["construct"].append(timings.get("previousConstruct", 0) / 1000)
    
    # Plot timing breakdown for each client
    for client, data in clients_data.items():
        _plot_client_time_breakdown(client, data, metrics_folder)


def _plot_client_time_breakdown(client, data, metrics_folder):
    """Plot time breakdown for a single client."""
    # Sort by round
    rounds = np.array(data["rounds"])
    sort_idx = np.argsort(rounds)
    
    rounds = rounds[sort_idx]
    training = np.array(data["training"])[sort_idx]
    parsing = np.array(data["parsing"])[sort_idx]
    construct = np.array(data["construct"])[sort_idx]
    
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    
    width = 0.25
    x = np.arange(len(rounds))
    
    plt.bar(x - width, training, width, label='Training')
    plt.bar(x, parsing, width, label='Parsing')
    plt.bar(x + width, construct, width, label='Model Construction')
    
    plt.title(f'Processing Time Breakdown for Client {client}', fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel('Round', fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel('Time (seconds)', fontsize=AXIS_LABEL_FONTSIZE)
    plt.xticks(x, [str(r) for r in rounds], fontsize=TICK_LABEL_FONTSIZE)
    plt.legend(fontsize=LEGEND_FONTSIZE, bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, axis='y', linestyle='--', alpha=0.7)
    
    _save_plot(metrics_folder, f"time_breakdown_client_{client}.png")


def plot_training_efficiency(json_data, metrics_folder):
    """Plot the relationship between training time, dataset size, and model performance."""
    training_times, dataset_sizes, accuracies, client_ids, epochs = [], [], [], [], []
    
    for item in json_data:
        if not _has_timing_data(item):
            continue
        
        try:
            training_times.append(item["timings"]["training"] / 1000)
            dataset_sizes.append(item["dataset_size"])
            accuracies.append(float(item["metrics"]["accuracy"]))
            client_ids.append(item["client"])
            epochs.append(item["epochs"])
        except (ValueError, TypeError):
            continue
    
    if not training_times:
        print("No valid training efficiency data found")
        return
    
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    
    scatter = plt.scatter(dataset_sizes, training_times, 
                         c=accuracies, s=np.array(epochs)*50, 
                         alpha=0.7, cmap='viridis')
    
    # Add labels for each point
    for i, client in enumerate(client_ids):
        plt.annotate(client, (dataset_sizes[i], training_times[i]), 
                    textcoords="offset points", xytext=(0, 10), ha='center')
    
    plt.colorbar(scatter, label='Accuracy')
    
    # Create legend for epochs
    unique_epochs = sorted(set(epochs))
    handles = [plt.scatter([], [], s=e*50, color='gray', alpha=0.7) for e in unique_epochs]
    plt.legend(handles, [f'{e} epoch(s)' for e in unique_epochs], 
              title="Training Epochs", loc="upper left", bbox_to_anchor=(1.05, 1), fontsize=LEGEND_FONTSIZE)
    
    plt.title('Training Time vs Dataset Size', fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel('Dataset Size (samples)', fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel('Training Time (seconds)', fontsize=AXIS_LABEL_FONTSIZE)
    plt.grid(True, linestyle='--', alpha=0.7)
    
    _save_plot(metrics_folder, "training_efficiency.png")


def plot_average_metrics(json_data, metrics_folder, metrics_to_plot):
    """Plot the average value of each metric across all clients for each round."""
    round_data = defaultdict(lambda: defaultdict(list))
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
                    continue
    
    # Calculate averages
    averages = {}
    for metric in metrics_to_plot:
        averages[metric] = []
        for round_num in all_rounds:
            values = round_data[round_num][metric]
            if values:
                avg = sum(values) / len(values)
                averages[metric].append((round_num, avg))
    
    _plot_combined_averages(averages, all_rounds, metrics_folder)
    _plot_individual_averages(averages, all_rounds, metrics_folder, metrics_to_plot)


def _plot_combined_averages(averages, all_rounds, metrics_folder):
    """Plot all average metrics in one chart."""
    # Use standardized figure size
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    
    for metric, points in averages.items():
        if points:
            points.sort(key=lambda x: x[0])
            rounds, values = zip(*points)
            plt.plot(rounds, values, 'o-', linewidth=STANDARD_LINEWIDTH, label=metric, markersize=STANDARD_MARKERSIZE)
    
    plt.title("Average Metrics Across All Clients by Round", fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel("Round", fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel("Average Metric Value", fontsize=AXIS_LABEL_FONTSIZE)
    plt.legend(fontsize=LEGEND_FONTSIZE, bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xticks(all_rounds, fontsize=TICK_LABEL_FONTSIZE)
    plt.yticks(fontsize=TICK_LABEL_FONTSIZE)
    
    _save_plot(metrics_folder, "plot_average_metrics.png")


def _plot_individual_averages(averages, all_rounds, metrics_folder, metrics_to_plot):
    """Plot individual average metric charts."""
    for metric in metrics_to_plot:
        if metric not in averages or not averages[metric]:
            continue
        
        # Use standardized figure size
        plt.figure(figsize=STANDARD_FIGURE_SIZE)
        points = sorted(averages[metric], key=lambda x: x[0])
        rounds, values = zip(*points) if points else ([], [])
        
        plt.plot(rounds, values, 'o-', linewidth=ANNOTATION_LINEWIDTH, color='blue', markersize=LARGE_MARKERSIZE)
        plt.title(f"Average {metric} Across All Clients by Round", fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
        plt.xlabel("Round", fontsize=AXIS_LABEL_FONTSIZE)
        plt.ylabel(f"Average {metric}", fontsize=AXIS_LABEL_FONTSIZE)
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.xticks(all_rounds, fontsize=TICK_LABEL_FONTSIZE)
        plt.yticks(fontsize=TICK_LABEL_FONTSIZE)
        
        # Add value annotations
        for round_num, value in zip(rounds, values):
            plt.annotate(f"{value:.3f}", (round_num, value),
                        textcoords="offset points", xytext=(0, 10), ha='center', fontsize=ANNOTATION_FONTSIZE)
        
        _save_plot(metrics_folder, f"plot_average_{metric}.png")


def plot_fixed_memory_metrics(json_data, metrics_folder):
    """Plot fixed memory metrics as a single bar chart showing average values."""
    fixed_metrics = defaultdict(list)
    clients = set()
    
    for item in json_data:
        if "memory" in item and "fixed" in item["memory"]:
            clients.add(item["client"])
            
            for metric_name, value in item["memory"]["fixed"].items():
                kb_value = (value / 1024) if (value and value > 0) else 0.0
                fixed_metrics[metric_name].append(kb_value)
    
    if not fixed_metrics:
        print("No fixed memory metrics found")
        return
    
    _plot_memory_bar_chart(fixed_metrics, clients, metrics_folder, "fixed_memory_metrics.png",
                          "Average Fixed Memory Metrics Across All Devices")


def plot_round_memory_metrics(json_data, metrics_folder):
    """Plot round-based memory metrics as line charts showing average evolution."""
    round_metrics = defaultdict(lambda: defaultdict(list))
    rounds = set()
    
    for item in json_data:
        if "memory" in item and "round" in item["memory"]:
            round_num = item.get("round", 0)
            rounds.add(round_num)
            
            for metric_name, value in item["memory"]["round"].items():
                kb_value = (value / 1024) if (value and value > 0) else 0.0
                round_metrics[metric_name][round_num].append(kb_value)
    
    if not round_metrics:
        print("No round memory metrics found")
        return
    
    _plot_memory_line_chart(round_metrics, sorted(rounds), metrics_folder)


def _plot_memory_bar_chart(metrics_data, clients, metrics_folder, filename, title):
    """Create a bar chart for memory metrics."""
    metric_names, metric_averages = [], []
    
    for metric_name, values in metrics_data.items():
        non_zero_values = [v for v in values if v > 0]
        avg_value = sum(non_zero_values) / len(non_zero_values) if non_zero_values else 0.0
        
        metric_names.append(metric_name.replace("_", " ").title())
        metric_averages.append(avg_value)
    
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    colors = plt.cm.Set3(np.linspace(0, 1, len(metric_names)))
    
    bars = plt.bar(metric_names, metric_averages, color=colors, alpha=0.8, 
                   edgecolor='black', linewidth=1)
    
    # Add value labels on top of bars
    for bar, value in zip(bars, metric_averages):
        height = bar.get_height()
        label = f'{value:.1f} KB' if height > 0 else 'N/A'
        color = 'black' if height > 0 else 'red'
        plt.text(bar.get_x() + bar.get_width()/2., height + max(metric_averages) * 0.01,
                label, ha='center', va='bottom', fontsize=ANNOTATION_FONTSIZE, fontweight='bold', color=color)
    
    plt.title(title, fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.ylabel('Memory (KB)', fontsize=AXIS_LABEL_FONTSIZE)
    plt.xlabel('Memory Metrics', fontsize=AXIS_LABEL_FONTSIZE)
    plt.grid(True, axis='y', linestyle='--', alpha=0.7)
    plt.xticks(rotation=45, ha='right')
    
    max_val = max(metric_averages) if metric_averages else 100
    plt.ylim(bottom=0, top=max_val * 1.15 if max_val > 0 else 100)
    
    plt.figtext(0.02, 0.02, f'Based on data from {len(clients)} clients', 
                fontsize=10, style='italic', alpha=0.7)
    
    _save_plot(metrics_folder, filename)


def _plot_memory_line_chart(round_metrics, rounds_list, metrics_folder):
    """Create a line chart for round-based memory metrics."""
    metric_averages = {}
    for metric_name, round_data in round_metrics.items():
        metric_averages[metric_name] = []
        
        for round_num in rounds_list:
            if round_num in round_data:
                values = round_data[round_num]
                non_zero_values = [v for v in values if v > 0]
                avg_value = sum(non_zero_values) / len(non_zero_values) if non_zero_values else 0.0
            else:
                avg_value = 0.0
            
            metric_averages[metric_name].append(avg_value)
    
    plt.figure(figsize=STANDARD_FIGURE_SIZE)
    
    colors = plt.cm.tab10(np.linspace(0, 1, len(metric_averages)))
    line_styles = ['-', '--', '-.', ':', '-', '--']
    markers = ['o', 's', '^', 'D', 'v', 'p']
    
    for idx, (metric_name, averages) in enumerate(metric_averages.items()):
        label = metric_name.replace("_", " ").title()
        plt.plot(rounds_list, averages, 
                color=colors[idx % len(colors)], 
                linestyle=line_styles[idx % len(line_styles)], 
                marker=markers[idx % len(markers)], 
                linewidth=STANDARD_LINEWIDTH + 0.5, markersize=LARGE_MARKERSIZE, label=label, alpha=0.8)
    
    plt.title('Average Round Memory Metrics Evolution Across Federation Rounds', 
              fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.ylabel('Memory (KB)', fontsize=AXIS_LABEL_FONTSIZE)
    plt.xlabel('Round', fontsize=AXIS_LABEL_FONTSIZE)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xticks(rounds_list, [f'Round {r}' for r in rounds_list], fontsize=TICK_LABEL_FONTSIZE)
    plt.legend(loc='upper left', frameon=True, fancybox=True, shadow=True, fontsize=LEGEND_FONTSIZE, bbox_to_anchor=(1.05, 1))
    
    all_values = [val for averages in metric_averages.values() for val in averages if val > 0]
    max_val = max(all_values) if all_values else 100
    plt.ylim(bottom=0, top=max_val * 1.2)
    
    _save_plot(metrics_folder, "round_memory_metrics.png")


def _has_timing_data(item):
    """Check if item has valid timing data."""
    return ("timings" in item and 
            isinstance(item["timings"], dict) and 
            "training" in item["timings"])


def _save_plot(metrics_folder, filename):
    """Save plot with consistent formatting and close figure."""
    plt.tight_layout()
    plt.savefig(metrics_folder + filename, dpi=STANDARD_DPI, bbox_inches='tight')
    print(f"Plot saved as {filename}")
    plt.close()