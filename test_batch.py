#!/usr/bin/env python3
"""
Test script for batch federated learning functionality
"""
import json
import os
import tempfile

def create_test_config():
    """Create a simple test configuration"""
    config = [
        {
            "name": "test_batch_1",
            "epochs": 1,
            "rounds": 1,
            "layers": [3, 10, 6],
            "activationFunctions": [2, 6],
            "learningRateWeights": 0.1,
            "learningRateBiases": 0.02,
            "seed": 42,
            "sendJsonWeights": False
        },
        {
            "name": "test_batch_2", 
            "epochs": 2,
            "rounds": 1,
            "layers": [3, 20, 15, 6],
            "activationFunctions": [1, 1, 6],
            "learningRateWeights": 0.08,
            "learningRateBiases": 0.016,
            "seed": 123,
            "sendJsonWeights": True
        }
    ]
    return config

def test_config_validation():
    """Test configuration validation"""
    print("Testing configuration validation...")
    
    # Import the server class
    import sys
    sys.path.append('/home/shirkit/Projects/Github/atlantico-server')
    from novoServidor import MQTTFederatedServer
    
    server = MQTTFederatedServer()
    
    # Test valid configuration
    valid_config = {
        "name": "test",
        "epochs": 5,
        "layers": [3, 10, 6],
        "activationFunctions": [2, 6],
        "learningRateWeights": 0.1,
        "learningRateBiases": 0.02,
        "seed": 42
    }
    
    result = server._validate_test_config(valid_config, 1)
    print(f"Valid config test: {'PASS' if result else 'FAIL'}")
    
    # Test invalid configuration (missing field)
    invalid_config = {
        "name": "test",
        "epochs": 5,
        "layers": [3, 10, 6],
        # Missing activationFunctions
        "learningRateWeights": 0.1,
        "learningRateBiases": 0.02,
        "seed": 42
    }
    
    result = server._validate_test_config(invalid_config, 2)
    print(f"Invalid config test: {'PASS' if not result else 'FAIL'}")
    
    print("Configuration validation tests completed.\n")

def test_config_file_creation():
    """Test creating and loading configuration file"""
    print("Testing configuration file creation and loading...")
    
    config = create_test_config()
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f, indent=2)
        temp_file = f.name
    
    try:
        # Test loading the file
        with open(temp_file, 'r') as f:
            loaded_config = json.load(f)
        
        print(f"Config file creation: PASS")
        print(f"Number of tests in config: {len(loaded_config)}")
        
        for i, test_config in enumerate(loaded_config):
            print(f"  Test {i+1}: {test_config['name']}")
            print(f"    Epochs: {test_config['epochs']}")
            print(f"    Layers: {test_config['layers']}")
            print(f"    Learning rates: W={test_config['learningRateWeights']}, B={test_config['learningRateBiases']}")
        
    finally:
        # Cleanup
        os.unlink(temp_file)
    
    print("Configuration file tests completed.\n")

def main():
    """Run all tests"""
    print("Starting batch federated learning tests...\n")
    
    try:
        test_config_validation()
        test_config_file_creation()
        print("All tests completed successfully!")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
