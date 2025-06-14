#!/usr/bin/env python3
"""
Test script to verify binary neural network aggregation functionality
"""

import sys
import os
sys.path.append('/home/shirkit/Projects/Github/atlantico-server')

from novoServidor import MQTTFederatedServer

def test_binary_reading():
    """Test reading binary .nn files"""
    server = MQTTFederatedServer()
    
    # Test with existing dummy files
    test_files = ['dummy1.nn', 'dummy2.nn']
    
    for filename in test_files:
        filepath = f'/home/shirkit/Projects/Github/atlantico-server/{filename}'
        if os.path.exists(filepath):
            print(f"\n=== Testing {filename} ===")
            network_data = server._read_binary_nn_file(filepath)
            
            if network_data:
                print(f"✅ Successfully read {filename}")
                print(f"   Number of layers: {network_data['numberOflayers']}")
                
                for i, layer in enumerate(network_data['layers']):
                    print(f"   Layer {i}: {layer['inputs']} -> {layer['outputs']}")
                    print(f"     Activation: {layer['activation_function']}")
                    print(f"     Biases shape: {layer['biases'].shape}")
                    print(f"     Weights shape: {layer['weights'].shape}")
                    print(f"     Sample bias: {layer['biases'][0]:.6f}")
                    print(f"     Sample weight: {layer['weights'][0][0]:.6f}")
            else:
                print(f"❌ Failed to read {filename}")
        else:
            print(f"⚠️  File not found: {filename}")

def test_aggregation():
    """Test aggregation functionality"""
    server = MQTTFederatedServer()
    
    # Set up a test directory
    os.makedirs('/tmp/test_aggregation', exist_ok=True)
    
    # Copy test files
    import shutil
    if os.path.exists('/home/shirkit/Projects/Github/atlantico-server/dummy1.nn'):
        shutil.copy('/home/shirkit/Projects/Github/atlantico-server/dummy1.nn', 
                   '/tmp/test_aggregation/client1.nn')
    if os.path.exists('/home/shirkit/Projects/Github/atlantico-server/dummy2.nn'):
        shutil.copy('/home/shirkit/Projects/Github/atlantico-server/dummy2.nn', 
                   '/tmp/test_aggregation/client2.nn')
    
    # Test aggregation
    print(f"\n=== Testing Aggregation ===")
    server.state.is_federated = False
    original_weights_folder = server.__class__.__dict__['WEIGHTS_FOLDER'] if hasattr(server.__class__, 'WEIGHTS_FOLDER') else '/tmp/test_aggregation'
    
    # Temporarily change the weights folder
    import novoServidor
    old_folder = novoServidor.WEIGHTS_FOLDER
    novoServidor.WEIGHTS_FOLDER = '/tmp/test_aggregation/'
    
    try:
        server.aggregate_weights()
        
        # Check if aggregated file was created
        output_file = '/tmp/test_aggregation/aggregated_weights.nn'
        if os.path.exists(output_file):
            print("✅ Aggregated file created successfully")
            
            # Test reading the aggregated file
            aggregated_data = server._read_binary_nn_file(output_file)
            if aggregated_data:
                print("✅ Aggregated file can be read back")
                print(f"   Number of layers: {aggregated_data['numberOflayers']}")
            else:
                print("❌ Cannot read aggregated file")
        else:
            print("❌ Aggregated file was not created")
            
    finally:
        # Restore original folder
        novoServidor.WEIGHTS_FOLDER = old_folder

if __name__ == "__main__":
    print("🧪 Testing Binary Neural Network Aggregation")
    print("=" * 50)
    
    test_binary_reading()
    test_aggregation()
    
    print("\n✅ Tests completed!")
