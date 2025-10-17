# Batch Federated Learning Configuration

This document explains how to use the batch processing feature for federated learning.

## Overview

The batch processing feature allows you to run multiple federated learning experiments sequentially using a single JSON configuration file. Each test in the batch can have different network architectures, training parameters, and configurations.

## Usage

### Command Line
```bash
python server.py batch --config path/to/config.json --clients 5
```

### Interactive Mode
```bash
python server.py
# Select 'batch' option
# Enter path to JSON configuration file
# Enter number of expected clients (optional)
```

## JSON Configuration Format

The configuration file must be a JSON array containing test objects. Each test object supports the following parameters:

### Required Parameters

- **`name`** (string): A descriptive name for the test
- **`epochs`** (integer): Number of training epochs per round
- **`layers`** (array of integers): Network layer sizes (e.g., [3, 40, 30, 6])
- **`activationFunctions`** (array of integers): Activation function codes for each layer transition
- **`learningRateWeights`** (number): Learning rate for weights
- **`learningRateBiases`** (number): Learning rate for biases
- **`seed`** (integer): Random seed for reproducibility

### Optional Parameters

- **`rounds`** (integer): Number of federated learning rounds (default: 1)
- **`sendJsonWeights`** (boolean): Whether to send weights in JSON format (default: false)

### Activation Function Codes

- `0` - Sigmoid
- `1` - Tanh
- `2` - ReLU
- `3` - Leaky ReLU
- `4` - ELU
- `5` - SELU
- `6` - Softmax

## Example Configuration

```json
[
  {
    "name": "small_network_test",
    "epochs": 5,
    "rounds": 3,
    "layers": [3, 20, 15, 6],
    "activationFunctions": [1, 1, 6],
    "learningRateWeights": 0.1,
    "learningRateBiases": 0.02,
    "seed": 42,
    "sendJsonWeights": false
  },
  {
    "name": "large_network_test",
    "epochs": 10,
    "rounds": 5,
    "layers": [3, 100, 80, 60, 40, 20, 6],
    "activationFunctions": [2, 2, 2, 2, 2, 6],
    "learningRateWeights": 0.05,
    "learningRateBiases": 0.01,
    "seed": 999,
    "sendJsonWeights": true
  }
]
```

## Execution Flow

1. **Configuration Loading**: The server loads and validates the JSON configuration
2. **Sequential Processing**: Each test is processed one after another
3. **Client Connection**: For each test, the server waits for clients to connect
4. **Federated Learning**: The normal federated learning process runs with the test-specific configuration
5. **Results Storage**: Results are saved in separate directories with timestamps and test names
6. **Error Handling**: If a test fails, the batch continues to the next test (non-blocking)
7. **Summary Report**: At the end, a summary shows successful vs failed tests
8. **Cleanup**: After each test, clients are properly notified and the next test begins

## Output Structure

Each batch run creates a separate batch directory with all tests organized inside:
```
weights/
├── batch_2025-06-26_14-30-15/          # Batch folder with timestamp
│   ├── batch_summary.json              # Summary of all tests in the batch
│   ├── 2025-06-26_14-30-16_small_network_test/
│   │   ├── config.json
│   │   ├── 0/ (round 0 data)
│   │   ├── 1/ (round 1 data)
│   │   ├── done.json
│   ├── 2025-06-26_14-35-22_medium_network_test/
│   │   ├── config.json
│   │   ├── 0/ (round 0 data)
│   │   ├── 1/ (round 1 data)
│   │   ├── failed.json (if test failed)
│   ├── 2025-06-26_14-40-18_large_network_test/
│   │   ├── config.json
│   │   ├── 0/ (round 0 data)
│   │   ├── done.json
├── batch_2025-06-26_16-15-30/          # Another batch run
│   ├── batch_summary.json
│   ├── ...
```

### Batch Summary File

Each batch creates a `batch_summary.json` file containing:
- Batch execution details (start/end times)
- Success/failure statistics
- Configuration file used
- Details of each test in the batch

## Error Handling

- **Configuration Validation**: Invalid configurations are skipped with error messages
- **Client Connection**: Tests fail if insufficient clients connect, but batch continues
- **Training Failures**: If a test fails, it's marked as failed and the batch continues to the next test
- **Partial Results**: Failed tests still save configuration and partial results
- **Early Detection**: NaN values and other issues are detected early and logged
- **Summary Reporting**: Final summary shows which tests succeeded and which failed
- **Robust Cleanup**: Proper cleanup happens even when tests fail unexpectedly

## Best Practices

1. **Test Ordering**: Start with simpler/smaller networks first
2. **Resource Management**: Allow sufficient time between tests for client recovery
3. **Backup Configurations**: Keep backup copies of your configuration files
4. **Monitoring**: Monitor logs for any issues during batch processing
5. **Client Capacity**: Ensure clients have sufficient resources for all planned tests

## Validation

The system validates:
- JSON syntax and structure
- Required fields presence
- Numeric parameter ranges
- Layer and activation function compatibility
- Client connection requirements

If any validation fails, the specific test is skipped and the error is logged.
