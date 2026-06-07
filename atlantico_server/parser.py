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
import logging

logger = logging.getLogger(__name__)

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
        logger.warning("No JSON files found in parse folder")
        return

    logger.info(f"Found {len(found_files)} JSON files")

    json_data = _load_json_data(found_files)
    if not json_data:
        logger.warning("No valid data was loaded")
        return

    logger.info("Data parsed successfully")
    if metrics_folder and not os.path.exists(metrics_folder):
        os.makedirs(metrics_folder)
    
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

def _find_nn_files(parse_folder):
    """Find all neural network files in the parse folder."""
    found_files = []
    for root, dirs, files in os.walk(parse_folder):
        for file in files:
            if file.endswith('.nn') and file != "aggregated_weights.nn":
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
                data["metrics"] = data["data"].get("metrics")
                data["client"] = data["data"].get("client")
                data["timings"] = data["data"].get("timings")
                data["dataset_size"] = data["data"].get("datasetSize")
                data["model"] = data["data"].get("model")
                data["epochs"] = data["data"].get("epochs")
                data["memory"] = data["data"].get("memory")
                data["data"] = None  # Clear original data to save memory
                
                json_data.append(data)
                
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {file}: {e}")
        except KeyError as e:
            logger.error(f"Missing key in {file}: {e}")
    
    return json_data


def _generate_all_plots(json_data, metrics_folder):
    """Generate all plots with error handling."""
    metrics_to_plot = ["meanSqrdError", "accuracy", "precision", "recall", "f1Score", "balancedAccuracy", "balancedPrecision", "balancedRecall", "balancedF1Score"]
    
    # Generate average metrics plot
    plot_average_metrics(json_data, metrics_folder, metrics_to_plot)
    
    # Generate individual metric plots
    for metric in metrics_to_plot:
        try:
            plot_metrics(json_data, metrics_folder, metric)
            plot_clients_heatmap(json_data, metrics_folder, metric)
        except Exception as e:
            logger.error(f"Error plotting {metric}: {e}")
    
    # Generate per-client plots
    for client_id in set(item["client"] for item in json_data):
        try:
            plot_multiple_metrics(json_data, client_id, metrics_folder, metrics_to_plot)
        except Exception as e:
            logger.error(f"Error plotting metrics for client {client_id}: {e}")

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
        plot_round_memory_metrics,
        plot_gradient_explosions  # Add gradient explosion plot
    ]
    
    for plot_func in performance_plots:
        try:
            plot_func(json_data, metrics_folder)
        except Exception as e:
            logger.error(f"Error in {plot_func.__name__}: {e}")
            logger.debug(traceback.format_exc())


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
        logger.debug(f"No data found for metric: {metric_name}")
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
        logger.debug(f"No data found for client: {client_id}")
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
        logger.debug(f"Insufficient data for heatmap: {len(clients)} clients, {len(rounds)} rounds")
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
        logger.debug("No valid training efficiency data found")
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
        logger.debug("No valid complexity vs speed data found")
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
        logger.debug("No client or round data found for combined processing time plot")
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
                    label=f"Client {client}", color=colors[i])
        
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
        logger.debug("No timing data found for average timing metrics")
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
        logger.debug("No valid training efficiency data found")
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
        logger.debug("No fixed memory metrics found")
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
        logger.debug("No round memory metrics found")
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


def plot_gradient_explosions(json_data, metrics_folder):
    """Plot gradient explosion occurrences by tracking null meanSqrdError values."""
    explosion_data = defaultdict(int)  # round -> count of explosions
    total_devices_per_round = defaultdict(int)  # round -> total devices
    all_rounds = sorted(set(item.get("round", 0) for item in json_data))
    
    # Count explosions and total devices per round
    for item in json_data:
        round_num = item.get("round", 0)
        total_devices_per_round[round_num] += 1
        
        # Check if meanSqrdError is null/None (gradient explosion indicator)
        mean_sqrd_error = item.get("metrics", {}).get("meanSqrdError")
        if mean_sqrd_error is None:
            explosion_data[round_num] += 1
    
    # Prepare data for plotting
    rounds = []
    explosion_counts = []
    explosion_percentages = []
    
    for round_num in all_rounds:
        rounds.append(round_num)
        count = explosion_data[round_num]
        total = total_devices_per_round[round_num]
        explosion_counts.append(count)
        explosion_percentages.append((count / total * 100) if total > 0 else 0)
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=LARGE_FIGURE_SIZE, sharex=True)
    
    # Plot 1: Absolute count of gradient explosions
    bars1 = ax1.bar(rounds, explosion_counts, color='red', alpha=0.7, 
                    edgecolor='darkred', linewidth=1)
    ax1.set_title("Gradient Explosions per Round", 
                 fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    ax1.set_ylabel("Number of Devices with Gradient Explosion", fontsize=AXIS_LABEL_FONTSIZE)
    ax1.grid(True, linestyle='--', alpha=0.7, axis='y')
    ax1.tick_params(axis='both', labelsize=TICK_LABEL_FONTSIZE)
    
    # Add value labels on bars
    for bar, count in zip(bars1, explosion_counts):
        if count > 0:
            ax1.annotate(f'{count}', (bar.get_x() + bar.get_width()/2, bar.get_height()),
                        ha='center', va='bottom', fontsize=ANNOTATION_FONTSIZE, 
                        fontweight='bold', color='darkred')
    
    # Plot 2: Percentage of devices with gradient explosions
    bars2 = ax2.bar(rounds, explosion_percentages, color='orange', alpha=0.7,
                    edgecolor='darkorange', linewidth=1)
    ax2.set_title("Percentage of Devices with Gradient Explosions per Round", 
                 fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    ax2.set_xlabel("Round", fontsize=AXIS_LABEL_FONTSIZE)
    ax2.set_ylabel("Percentage of Devices (%)", fontsize=AXIS_LABEL_FONTSIZE)
    ax2.grid(True, linestyle='--', alpha=0.7, axis='y')
    ax2.tick_params(axis='both', labelsize=TICK_LABEL_FONTSIZE)
    ax2.set_ylim(0, 100)
    
    # Add percentage labels on bars
    for bar, percentage in zip(bars2, explosion_percentages):
        if percentage > 0:
            ax2.annotate(f'{percentage:.1f}%', (bar.get_x() + bar.get_width()/2, bar.get_height()),
                        ha='center', va='bottom', fontsize=ANNOTATION_FONTSIZE, 
                        fontweight='bold', color='darkorange')
    
    # Set x-axis ticks to show all rounds
    plt.xticks(all_rounds, fontsize=TICK_LABEL_FONTSIZE)
    
    # Add summary statistics as text
    total_explosions = sum(explosion_counts)
    total_measurements = sum(total_devices_per_round.values())
    overall_percentage = (total_explosions / total_measurements * 100) if total_measurements > 0 else 0
    
    summary_text = f"Summary: {total_explosions} explosions out of {total_measurements} measurements ({overall_percentage:.1f}%)"
    fig.suptitle(summary_text, fontsize=ANNOTATION_FONTSIZE, y=0.02)
    
    _save_plot(metrics_folder, "gradient_explosions.png")


def _has_timing_data(item):
    """Check if item has valid timing data."""
    return ("timings" in item and 
            isinstance(item["timings"], dict) and 
            "training" in item["timings"])


def _save_plot(metrics_folder, filename):
    """Save plot with consistent formatting and close figure."""
    plt.tight_layout()
    plt.savefig(os.path.join(metrics_folder, filename), dpi=STANDARD_DPI, bbox_inches='tight')
    logger.debug(f"Plot saved as {filename}")
    plt.close()


def plot_batch_comparison(batch_folder, metrics_folder=None):
    """
    Compare average metrics across multiple batch tests.
    
    Args:
        batch_folder: Path to the batch folder containing multiple test subfolders
        metrics_folder: Path where comparison plots will be saved (optional, defaults to batch_folder/metrics/)
    """
    logger.debug(f"Starting batch comparison for folder: {batch_folder}")
    
    # Set default metrics folder if not provided
    if metrics_folder is None:
        metrics_folder = os.path.join(batch_folder, "metrics")
    
    # Create metrics folder if it doesn't exist
    if not os.path.exists(metrics_folder):
        os.makedirs(metrics_folder)
        logger.debug(f"Created metrics folder: {metrics_folder}")
    
    # Find all test subfolders in the batch folder
    test_folders = []
    if os.path.exists(batch_folder):
        for item in os.listdir(batch_folder):
            item_path = os.path.join(batch_folder, item)
            if os.path.isdir(item_path) and not item.startswith('.') and item != 'metrics':
                # Check if this is a test folder (has done.json)
                done_json_path = os.path.join(item_path, "done.json")
                if os.path.exists(done_json_path):
                    # This is a valid test folder, use it directly
                    test_folders.append((item, item_path))
    
    if not test_folders:
        logger.warning("No test folders with parse subfolders found in batch folder")
        return
    
    logger.debug(f"Found {len(test_folders)} test folders")
    
    # Load data from all tests
    all_test_data = {}
    metrics_to_plot = ["accuracy", "precision", "f1Score", "recall", "meanSqrdError", "balancedAccuracy", "balancedPrecision", "balancedRecall", "balancedF1Score"]
    
    for test_name, parse_path in test_folders:
        logger.debug(f"Processing test: {test_name}")
        found_files = _find_json_files(parse_path)
        if found_files:
            json_data = _load_json_data(found_files)
            if json_data:
                # Calculate average metrics for this test
                test_averages = _calculate_test_averages(json_data, metrics_to_plot)
                all_test_data[test_name] = test_averages
    
    if not all_test_data:
        logger.warning("No valid data found in any test folder")
        return
    
    # Create comparison plots
    _plot_batch_metric_comparisons(all_test_data, metrics_folder, metrics_to_plot)
    _plot_batch_combined_comparison(all_test_data, metrics_folder, metrics_to_plot)
    _plot_batch_gradient_explosions(test_folders, metrics_folder)


def _calculate_test_averages(json_data, metrics_to_plot):
    """Calculate average metrics across all clients for each round in a test."""
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
    
    # Calculate averages for each round
    test_averages = {}
    for metric in metrics_to_plot:
        test_averages[metric] = []
        for round_num in all_rounds:
            values = round_data[round_num][metric]
            if values:
                avg = sum(values) / len(values)
                test_averages[metric].append((round_num, avg))
    
    return test_averages


def _plot_batch_metric_comparisons(all_test_data, metrics_folder, metrics_to_plot):
    """Create individual comparison plots for each metric across all tests."""
    for metric in metrics_to_plot:
        plt.figure(figsize=LARGE_FIGURE_SIZE)
        
        # Define colors for different tests
        colors = plt.cm.tab10(np.linspace(0, 1, len(all_test_data)))
        
        for i, (test_name, test_data) in enumerate(all_test_data.items()):
            if metric in test_data and test_data[metric]:
                points = sorted(test_data[metric], key=lambda x: x[0])
                rounds, values = zip(*points) if points else ([], [])
                
                plt.plot(rounds, values, 'o-', 
                        linewidth=STANDARD_LINEWIDTH, 
                        color=colors[i],
                        label=test_name, 
                        markersize=STANDARD_MARKERSIZE)
        
        plt.title(f"Batch Comparison - Average {metric} Across All Tests", 
                 fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
        plt.xlabel("Round", fontsize=AXIS_LABEL_FONTSIZE)
        plt.ylabel(f"Average {metric}", fontsize=AXIS_LABEL_FONTSIZE)
        plt.legend(fontsize=LEGEND_FONTSIZE, bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.xticks(fontsize=TICK_LABEL_FONTSIZE)
        plt.yticks(fontsize=TICK_LABEL_FONTSIZE)
        
        _save_plot(metrics_folder, f"batch_comparison_{metric}.png")


def _plot_batch_combined_comparison(all_test_data, metrics_folder, metrics_to_plot):
    """Create a combined plot showing all metrics for all tests."""
    # Create subplots for each metric
    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    fig.suptitle("Batch Comparison - All Metrics Across All Tests", 
                fontsize=TITLE_FONTSIZE + 2, fontweight=TITLE_FONTWEIGHT)
    
    # Flatten axes for easier indexing
    axes_flat = axes.flatten()
    
    # Define colors for different tests
    colors = plt.cm.tab10(np.linspace(0, 1, len(all_test_data)))
    legend_handles = []
    legend_labels = []
    
    for metric_idx, metric in enumerate(metrics_to_plot):
        ax = axes_flat[metric_idx]
        
        for test_idx, (test_name, test_data) in enumerate(all_test_data.items()):
            if metric in test_data and test_data[metric]:
                points = sorted(test_data[metric], key=lambda x: x[0])
                rounds, values = zip(*points) if points else ([], [])
                
                line = ax.plot(rounds, values, 'o-', 
                              linewidth=STANDARD_LINEWIDTH, 
                              color=colors[test_idx],
                              label=test_name, 
                              markersize=STANDARD_MARKERSIZE)
                
                # Collect legend info from the first metric only to avoid duplicates
                if metric_idx == 0 and line:
                    legend_handles.append(line[0])
                    legend_labels.append(test_name)
        
        ax.set_title(f"Average {metric}", fontsize=AXIS_LABEL_FONTSIZE, fontweight='bold')
        ax.set_xlabel("Round", fontsize=TICK_LABEL_FONTSIZE)
        ax.set_ylabel(f"Average {metric}", fontsize=TICK_LABEL_FONTSIZE)
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.tick_params(axis='both', labelsize=TICK_LABEL_FONTSIZE - 1)
    
    # Hide the last subplot if we have an odd number of metrics
    if len(metrics_to_plot) < len(axes_flat):
        # Clear the last subplot but keep it visible for the legend
        axes_flat[-1].clear()
        axes_flat[-1].set_xticks([])
        axes_flat[-1].set_yticks([])
        axes_flat[-1].spines['top'].set_visible(False)
        axes_flat[-1].spines['right'].set_visible(False)
        axes_flat[-1].spines['bottom'].set_visible(False)
        axes_flat[-1].spines['left'].set_visible(False)
        
        # Place legend in the empty bottom-right subplot area
        if legend_handles and legend_labels:
            axes_flat[-1].legend(legend_handles, legend_labels, fontsize=LEGEND_FONTSIZE - 1, 
                               loc='center', frameon=True, fancybox=True, shadow=True)
    else:
        # If all subplots are used, place legend in bottom-right corner of the figure
        if legend_handles and legend_labels:
            fig.legend(legend_handles, legend_labels, fontsize=LEGEND_FONTSIZE - 1, 
                      loc='lower right', bbox_to_anchor=(0.98, 0.02))
    
    plt.tight_layout()
    plt.savefig(os.path.join(metrics_folder, "batch_comparison_combined.png"), 
                dpi=STANDARD_DPI, bbox_inches='tight')
    logger.debug("Plot saved as batch_comparison_combined.png")
    plt.close()


def _plot_batch_gradient_explosions(test_folders, metrics_folder):
    """Create a line plot showing gradient explosions across all batch tests."""
    plt.figure(figsize=LARGE_FIGURE_SIZE)
    
    # Define colors for different tests
    colors = plt.cm.tab10(np.linspace(0, 1, len(test_folders)))
    
    # Track all rounds across all tests to get consistent x-axis
    all_rounds = set()
    explosion_data = {}
    
    # Process each test to count gradient explosions per round
    for test_name, test_path in test_folders:
        logger.debug(f"Processing gradient explosions for test: {test_name}")
        found_files = _find_json_files(test_path)
        if found_files:
            json_data = _load_json_data(found_files)
            if json_data:
                round_explosions = defaultdict(int)
                
                # Count explosions per round
                for item in json_data:
                    round_num = item.get("round", 0)
                    all_rounds.add(round_num)
                    
                    # Check if meanSqrdError is null (gradient explosion)
                    if item.get("metrics", {}).get("meanSqrdError") is None:
                        round_explosions[round_num] += 1
                
                explosion_data[test_name] = round_explosions
    
    if not explosion_data:
        logger.debug("No gradient explosion data found for batch comparison")
        return
    
    all_rounds = sorted(all_rounds)
    
    # Calculate total explosions per test for summary
    total_explosions = {}
    for test_name, round_explosions in explosion_data.items():
        total_explosions[test_name] = sum(round_explosions.values())
    
    # Plot lines for each test
    for i, (test_name, round_explosions) in enumerate(explosion_data.items()):
        # Create data points for all rounds (0 if no explosions)
        explosion_counts = [round_explosions.get(round_num, 0) for round_num in all_rounds]
        total = total_explosions[test_name]
        
        # Add total to label
        label_with_total = f"{test_name} (Total: {total})"
        
        plt.plot(all_rounds, explosion_counts, 'o-', 
                linewidth=STANDARD_LINEWIDTH, 
                color=colors[i],
                label=label_with_total, 
                markersize=STANDARD_MARKERSIZE)
    
    plt.title("Batch Comparison - Gradient Explosions per Round", 
             fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.xlabel("Round", fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel("Number of Devices with Gradient Explosion", fontsize=AXIS_LABEL_FONTSIZE)
    plt.legend(fontsize=LEGEND_FONTSIZE - 2, bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.xticks(all_rounds, fontsize=TICK_LABEL_FONTSIZE)
    plt.yticks(fontsize=TICK_LABEL_FONTSIZE)
    
    # Set y-axis to start at 0 and use integer ticks
    plt.ylim(bottom=0)
    max_explosions = max([max(explosions.values()) if explosions else 0 
                         for explosions in explosion_data.values()])
    if max_explosions > 0:
        plt.yticks(range(0, max_explosions + 1))
    
    # Add summary text box
    summary_text = "Summary - Total Gradient Explosions:\n"
    sorted_totals = sorted(total_explosions.items(), key=lambda x: x[1], reverse=True)
    for test_name, total in sorted_totals:
        summary_text += f"• {test_name}: {total}\n"
    
    # Add text box with summary outside plot area (bottom right of figure)
    plt.figtext(0.98, 0.02, summary_text, 
                fontsize=ANNOTATION_FONTSIZE, verticalalignment='bottom', horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))
    
    _save_plot(metrics_folder, "batch_comparison_gradient_explosions.png")
    
    # Also create a heatmap version
    _create_gradient_explosions_heatmap(explosion_data, all_rounds, metrics_folder)


def _create_gradient_explosions_heatmap(explosion_data, all_rounds, metrics_folder):
    """Create a heatmap showing gradient explosions per test and round."""
    if not explosion_data:
        logger.debug("No gradient explosion data found for heatmap generation")
        return
    
    # Prepare data for heatmap
    test_names = sorted(explosion_data.keys())
    
    # Calculate totals for each test
    test_totals = {}
    for test_name in test_names:
        test_totals[test_name] = sum(explosion_data[test_name].values())
    
    # Sort test names by total explosions (descending)
    test_names = sorted(test_names, key=lambda x: test_totals[x], reverse=True)
    
    # Create matrix for heatmap
    heatmap_data = []
    test_labels_with_totals = []
    for test_name in test_names:
        row = []
        for round_num in all_rounds:
            explosions = explosion_data[test_name].get(round_num, 0)
            row.append(explosions)
        heatmap_data.append(row)
        # Add total to the test name label
        test_labels_with_totals.append(f"{test_name} (Total: {test_totals[test_name]})")
    
    # Create heatmap
    plt.figure(figsize=(max(12, len(all_rounds) * 0.8), max(8, len(test_names) * 0.5)))
    
    # Convert to numpy array for easier handling
    heatmap_array = np.array(heatmap_data)
    
    # Create heatmap with colorbar
    im = plt.imshow(heatmap_array, cmap='Reds', aspect='auto', interpolation='nearest')
    
    # Set ticks and labels
    plt.xticks(range(len(all_rounds)), all_rounds, fontsize=TICK_LABEL_FONTSIZE)
    plt.yticks(range(len(test_names)), test_labels_with_totals, fontsize=TICK_LABEL_FONTSIZE - 1)
    
    # Add colorbar
    cbar = plt.colorbar(im)
    cbar.set_label('Number of Gradient Explosions', rotation=270, labelpad=20, 
                   fontsize=AXIS_LABEL_FONTSIZE)
    
    # Add text annotations on heatmap
    for i in range(len(test_names)):
        for j in range(len(all_rounds)):
            value = heatmap_array[i, j]
            if value > 0:  # Only show non-zero values
                text_color = 'white' if value > heatmap_array.max() * 0.6 else 'black'
                plt.text(j, i, str(int(value)), ha='center', va='center', 
                        color=text_color, fontweight='bold', fontsize=10)
    
    plt.xlabel('Round', fontsize=AXIS_LABEL_FONTSIZE)
    plt.ylabel('Test', fontsize=AXIS_LABEL_FONTSIZE)
    plt.title('Gradient Explosions Heatmap: Tests vs Rounds', 
             fontsize=TITLE_FONTSIZE, fontweight=TITLE_FONTWEIGHT, pad=TITLE_PAD)
    plt.tight_layout()
    
    _save_plot(metrics_folder, "batch_comparison_gradient_explosions_heatmap.png")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  For regular parsing: python parser.py <parse_folder> <metrics_folder>")
        print("  For batch comparison: python parser.py --batch <batch_folder> [metrics_folder]")
        sys.exit(1)
    
    if sys.argv[1] == "--batch":
        if len(sys.argv) < 3 or len(sys.argv) > 4:
            print("Usage for batch comparison: python parser.py --batch <batch_folder> [metrics_folder]")
            print("  metrics_folder is optional - defaults to <batch_folder>/metrics/")
            sys.exit(1)
        
        batch_folder = sys.argv[2]
        metrics_folder = sys.argv[3] if len(sys.argv) == 4 else None
        
        plot_batch_comparison(batch_folder, metrics_folder)
        print("Batch comparison completed!")
    
    elif sys.argv[1] in ["-h", "--help"]:
        print("Usage:")
        print("  For regular parsing: python parser.py <parse_folder> <metrics_folder>")
        print("  For batch comparison: python parser.py --batch <batch_folder> [metrics_folder]")
        print("    metrics_folder is optional - defaults to <batch_folder>/metrics/")
        sys.exit(0)
    
    else:
        # Regular parsing mode
        if len(sys.argv) != 3:
            print("Usage for regular parsing: python parser.py <parse_folder> <metrics_folder>")
            sys.exit(1)
            
        parse_folder = sys.argv[1]
        metrics_folder = sys.argv[2]
        
        do_parse(parse_folder, metrics_folder)
        print("Parsing completed!")