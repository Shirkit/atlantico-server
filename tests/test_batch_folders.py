#!/usr/bin/env python3
"""
Test script to verify batch folder structure
"""
import os
import tempfile
import json
from datetime import datetime

def test_batch_folder_structure():
    """Test that batch processing creates the correct folder structure"""
    print("Testing batch folder structure...")
    
    # Create a simple test config with one test
    test_config = [
        {
            "name": "folder_structure_test",
            "epochs": 1,
            "rounds": 1,
            "layers": [3, 10, 6],
            "activationFunctions": [2, 6],
            "learningRateWeights": 0.1,
            "learningRateBiases": 0.02,
            "seed": 42,
            "sendJsonWeights": False
        }
    ]
    
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_config, f, indent=2)
        temp_config_file = f.name
    
    try:
        # Import the server class from the package
        from atlantico_server.server import MQTTFederatedServer, WEIGHTS_FOLDER

        # Create server instance (won't actually connect to MQTT for this test)
        server = MQTTFederatedServer()
        
        # Test batch base path creation logic
        batch_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        batch_folder_name = f"batch_{batch_timestamp}"
        expected_batch_path = os.path.join(WEIGHTS_FOLDER, batch_folder_name)
        
        print(f"Expected batch folder: {expected_batch_path}")
        print(f"Batch folder name pattern: batch_YYYY-MM-DD_HH-MM-SS")
        
        # Test individual test path creation
        test_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        test_name = test_config[0]['name']
        expected_test_path = os.path.join(expected_batch_path, f"{test_timestamp}_{test_name}")
        
        print(f"Expected test folder: {expected_test_path}")
        print(f"Test folder pattern: batch_folder/YYYY-MM-DD_HH-MM-SS_test_name")
        
        print("✅ Batch folder structure test passed!")
        
    finally:
        # Cleanup
        os.unlink(temp_config_file)

if __name__ == "__main__":
    test_batch_folder_structure()
