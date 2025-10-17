#!/usr/bin/env python3
"""
JSON to CSV Converter for Federated Learning Results

This script converts federated learning JSON outputs from individual device files
into a structured CSV format for analysis. It processes run folders containing:
- config.json: Configuration for the experiment
- done.json: Completion status
- Numbered folders (0, 1, 2, ...): Each representing a round
- Device JSON files (esp00.json, esp01.json, etc.): Results for each device

Output CSV format matches the structure:
client,execucao,rodada,accuracy,precision,recall,f1Score,meanSqrdError,datasetSize,training_time_ms,minFreeHeapAfterSetup,minimumFreeDuringRound
"""

import os
import json
import csv
import argparse
from datetime import datetime
from pathlib import Path
import sys

def load_json_file(filepath):
    """Load and parse a JSON file safely."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        print(f"Warning: Could not load {filepath}: {e}")
        return None

def extract_execution_number(run_folder_name, config_data):
    """Extract execution number from run folder name or config."""
    # Try to get from config first
    if config_data and 'batch_test_number' in config_data:
        return config_data['batch_test_number']
    
    # Try to extract from folder name pattern: YYYY-MM-DD_HH-MM-SS_test_name
    parts = run_folder_name.split('_')
    if len(parts) >= 3:
        try:
            # Look for numeric patterns in the folder name
            for part in parts:
                if part.isdigit():
                    return int(part)
        except ValueError:
            pass
    
    # Default to 1 if no execution number found
    return 1

def is_valid_run_folder(folder_path):
    """Check if a folder is a valid run folder (has config.json and done.json)."""
    config_path = os.path.join(folder_path, 'config.json')
    done_path = os.path.join(folder_path, 'done.json')
    return os.path.isfile(config_path) and os.path.isfile(done_path)

def get_round_folders(run_folder):
    """Get all numeric round folders in a run folder."""
    round_folders = []
    try:
        for item in os.listdir(run_folder):
            item_path = os.path.join(run_folder, item)
            if os.path.isdir(item_path) and item.isdigit():
                round_folders.append((int(item), item_path))
    except OSError as e:
        print(f"Error reading run folder {run_folder}: {e}")
        return []
    
    # Sort by round number
    round_folders.sort(key=lambda x: x[0])
    return round_folders

def get_device_json_files(round_folder):
    """Get all device JSON files in a round folder."""
    device_files = []
    try:
        for item in os.listdir(round_folder):
            if item.endswith('.json') and item.startswith('esp'):
                device_name = item.replace('.json', '')
                device_files.append((device_name, os.path.join(round_folder, item)))
    except OSError as e:
        print(f"Error reading round folder {round_folder}: {e}")
        return []
    
    # Sort by device name
    device_files.sort(key=lambda x: x[0])
    return device_files

def extract_device_data(device_json_path, execution_num, round_num):
    """Extract relevant data from a device JSON file."""
    data = load_json_file(device_json_path)
    if not data or 'data' not in data:
        return None
    
    device_data = data['data']
    
    # Extract basic info
    client = device_data.get('client', 'unknown')
    
    # Extract metrics
    metrics = device_data.get('metrics', {})
    accuracy = metrics.get('accuracy', 0.0)
    precision = metrics.get('precision', 0.0)
    recall = metrics.get('recall', 0.0)
    f1_score = metrics.get('f1Score', 0.0)
    # Handle None values for meanSqrdError (gradient explosion cases)
    mean_sqrd_error = metrics.get('meanSqrdError')
    if mean_sqrd_error is None:
        mean_sqrd_error = float('nan')  # Use NaN for gradient explosions
    
    # Extract other data
    dataset_size = device_data.get('datasetSize', 0)
    
    # Extract timing data (convert to milliseconds if needed)
    timings = device_data.get('timings', {})
    training_time_ms = timings.get('training', 0)
    
    # Extract memory data
    memory = device_data.get('memory', {})
    fixed_memory = memory.get('fixed', {})
    round_memory = memory.get('round', {})
    
    min_free_heap_after_setup = fixed_memory.get('minFreeHeapAfterSetup', 0)
    minimum_free_during_round = round_memory.get('minimumFree', 0)
    
    return {
        'client': client,
        'execucao': execution_num,
        'rodada': round_num,
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1Score': f1_score,
        'meanSqrdError': mean_sqrd_error,
        'datasetSize': dataset_size,
        'training_time_ms': training_time_ms,
        'minFreeHeapAfterSetup': min_free_heap_after_setup,
        'minimumFreeDuringRound': minimum_free_during_round
    }

def calculate_average_row(all_data, execution_num):
    """Calculate average values across all devices and rounds for an execution."""
    if not all_data:
        return None
    
    # Group by round to calculate averages
    rounds_data = {}
    for row in all_data:
        round_num = row['rodada']
        if round_num not in rounds_data:
            rounds_data[round_num] = []
        rounds_data[round_num].append(row)
    
    # Calculate overall averages
    import math
    total_accuracy = sum(row['accuracy'] for row in all_data)
    total_precision = sum(row['precision'] for row in all_data)
    total_recall = sum(row['recall'] for row in all_data)
    total_f1_score = sum(row['f1Score'] for row in all_data)
    
    # Handle meanSqrdError with potential NaN values
    valid_mean_sqrd_errors = [row['meanSqrdError'] for row in all_data if not math.isnan(row['meanSqrdError'])]
    total_mean_sqrd_error = sum(valid_mean_sqrd_errors) if valid_mean_sqrd_errors else 0.0
    
    total_dataset_size = sum(row['datasetSize'] for row in all_data)
    total_training_time = sum(row['training_time_ms'] for row in all_data)
    total_min_heap = sum(row['minFreeHeapAfterSetup'] for row in all_data)
    total_min_during_round = sum(row['minimumFreeDuringRound'] for row in all_data)
    
    count = len(all_data)
    valid_mean_sqrd_count = len(valid_mean_sqrd_errors) if valid_mean_sqrd_errors else count
    
    return {
        'client': 'media',
        'execucao': execution_num,
        'rodada': '',  # Empty for average row
        'accuracy': total_accuracy / count,
        'precision': total_precision / count,
        'recall': total_recall / count,
        'f1Score': total_f1_score / count,
        'meanSqrdError': total_mean_sqrd_error / valid_mean_sqrd_count if valid_mean_sqrd_count > 0 else float('nan'),
        'datasetSize': total_dataset_size / count,
        'training_time_ms': total_training_time / count,
        'minFreeHeapAfterSetup': total_min_heap / count,
        'minimumFreeDuringRound': total_min_during_round / count
    }

def process_run_folder(run_folder_path, include_averages=True, verbose=False):
    """Process a single run folder and extract all device data."""
    if verbose:
        print(f"Processing run folder: {run_folder_path}")
    
    # Load config to get execution number and other metadata
    config_path = os.path.join(run_folder_path, 'config.json')
    config_data = load_json_file(config_path)
    
    if not config_data:
        if verbose:
            print(f"Warning: Could not load config.json from {run_folder_path}")
        return []
    
    # Extract execution number
    run_folder_name = os.path.basename(run_folder_path)
    execution_num = extract_execution_number(run_folder_name, config_data)
    
    # Get all round folders
    round_folders = get_round_folders(run_folder_path)
    if not round_folders:
        if verbose:
            print(f"Warning: No round folders found in {run_folder_path}")
        return []
    
    all_data = []
    
    # Process each round
    for round_num, round_folder_path in round_folders:
        if verbose:
            print(f"  Processing round {round_num}")
        
        # Get all device JSON files in this round
        device_files = get_device_json_files(round_folder_path)
        
        round_count = 0
        for device_name, device_json_path in device_files:
            device_data = extract_device_data(device_json_path, execution_num, round_num)
            if device_data:
                all_data.append(device_data)
                round_count += 1
        
        if verbose:
            print(f"    Found {round_count} devices")
    
    # Add average row if requested
    if include_averages and all_data:
        avg_row = calculate_average_row(all_data, execution_num)
        if avg_row:
            all_data.append(avg_row)
    
    if verbose:
        print(f"  Total rows extracted: {len(all_data)}")
    return all_data

def find_run_folders(search_path):
    """Find all valid run folders recursively in the given path."""
    run_folders = []
    
    if not os.path.exists(search_path):
        print(f"Error: Path {search_path} does not exist")
        return []
    
    print(f"Searching for run folders in: {search_path}")
    
    # Search for run folders recursively
    for root, dirs, files in os.walk(search_path):
        if is_valid_run_folder(root):
            run_folders.append(root)
            # Don't search subdirectories of a run folder to avoid nested processing
            dirs.clear()
    
    # Sort folders for consistent processing order
    run_folders.sort()
    return run_folders

def write_csv(data, output_path, verbose=False):
    """Write data to CSV file."""
    if not data:
        if verbose:
            print("No data to write")
        return False
    
    fieldnames = [
        'client', 'execucao', 'rodada', 'accuracy', 'precision', 'recall', 
        'f1Score', 'meanSqrdError', 'datasetSize', 'training_time_ms', 
        'minFreeHeapAfterSetup', 'minimumFreeDuringRound'
    ]
    
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        if verbose:
            print(f"CSV file written successfully: {output_path}")
            print(f"Total rows: {len(data)}")
        return True
    except Exception as e:
        if verbose:
            print(f"Error writing CSV file: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Convert federated learning JSON outputs to CSV format",
        epilog="""
Examples:
  # Process all runs in a folder tree (outputs CSV to each run folder)
  python json_to_csv_converter.py /path/to/folder/tree
  
  # Process with verbose output
  python json_to_csv_converter.py /path/to/folder/tree --verbose
  
  # Process without average rows
  python json_to_csv_converter.py /path/to/folder/tree --no-averages
  
  # Custom CSV filename (default: results.csv)
  python json_to_csv_converter.py /path/to/folder/tree --output-filename custom_results.csv
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('input_path', help='Path to folder tree containing run folders')
    parser.add_argument('--output-filename', default='results.csv',
                        help='Name of CSV file to create in each run folder (default: results.csv)')
    parser.add_argument('--no-averages', action='store_true', 
                        help='Do not include average rows in output')
    parser.add_argument('--verbose', '-v', action='store_true', 
                        help='Enable verbose output')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed without actually creating CSV files')
    
    args = parser.parse_args()
    
    # Validate input path
    if not os.path.exists(args.input_path):
        print(f"Error: Input path {args.input_path} does not exist")
        sys.exit(1)
    
    # Find all run folders recursively
    run_folders = find_run_folders(args.input_path)
    if not run_folders:
        print(f"No valid run folders found in {args.input_path}")
        print("A valid run folder must contain both config.json and done.json files")
        sys.exit(1)
    
    print(f"Found {len(run_folders)} run folder(s) to process")
    if args.verbose:
        for folder in run_folders:
            print(f"  - {folder}")
    
    if args.dry_run:
        print("\nDry run mode - no CSV files will be created")
        for run_folder in run_folders:
            output_path = os.path.join(run_folder, args.output_filename)
            print(f"Would create: {output_path}")
        return
    
    # Process each run folder individually
    include_averages = not args.no_averages
    successful_conversions = 0
    failed_conversions = 0
    
    for i, run_folder in enumerate(run_folders, 1):
        print(f"\n[{i}/{len(run_folders)}] Processing: {run_folder}")
        
        try:
            # Process the run folder
            run_data = process_run_folder(run_folder, include_averages, args.verbose)
            
            if not run_data:
                print(f"  Warning: No data extracted from {run_folder}")
                failed_conversions += 1
                continue
            
            # Create CSV in the same folder as config.json
            output_path = os.path.join(run_folder, args.output_filename)
            
            # Write CSV for this specific run
            success = write_csv(run_data, output_path, args.verbose)
            if success:
                successful_conversions += 1
                print(f"  ✅ Created: {output_path}")
            else:
                failed_conversions += 1
                print(f"  ❌ Failed to create: {output_path}")
                
        except Exception as e:
            print(f"  ❌ Error processing {run_folder}: {e}")
            failed_conversions += 1
            if args.verbose:
                import traceback
                traceback.print_exc()
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Conversion Summary:")
    print(f"  Total run folders found: {len(run_folders)}")
    print(f"  Successful conversions: {successful_conversions}")
    print(f"  Failed conversions: {failed_conversions}")
    print(f"  CSV filename used: {args.output_filename}")
    
    if failed_conversions > 0:
        print(f"\n⚠️  {failed_conversions} conversion(s) failed. Use --verbose for detailed error information.")
        sys.exit(1)
    else:
        print(f"\n🎉 All conversions completed successfully!")

if __name__ == "__main__":
    main()
