#!/usr/bin/env python3

import struct
import numpy as np

def read_nn_binary_with_activation(filepath):
    """
    Read ESP32 neural network binary file with activation function support
    This reader can handle both formats:
    - With ACTIVATION__PER_LAYER: includes activation bytes
    - Without ACTIVATION__PER_LAYER: no activation bytes
    """
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        
        print(f"Reading {filepath} ({len(data)} bytes)")
        offset = 0
        
        # Read number of layers
        if offset + 4 > len(data):
            raise ValueError("File too short for layer count")
        num_layers = struct.unpack('<I', data[offset:offset+4])[0]
        offset += 4
        print(f"Number of layers: {num_layers}")
        
        layers = []
        
        for layer_idx in range(num_layers):
            print(f"\n--- Layer {layer_idx} ---")
            
            # Try to detect if activation function byte is present
            # We'll use heuristics: reasonable activation value (0-6) and sensible layer dimensions
            activation_byte = None
            
            # Read potential activation byte
            if offset + 1 <= len(data):
                potential_activation = struct.unpack('<B', data[offset:offset+1])[0]
                
                # Check if this looks like an activation function (0-6 are valid)
                if 0 <= potential_activation <= 6:
                    # Look ahead to see if the next 8 bytes look like reasonable layer dimensions
                    if offset + 9 <= len(data):
                        try:
                            inputs = struct.unpack('<I', data[offset+1:offset+5])[0]
                            outputs = struct.unpack('<I', data[offset+5:offset+9])[0]
                            
                            # If dimensions look reasonable, assume activation byte is present
                            if (1 <= inputs <= 1000) and (1 <= outputs <= 1000):
                                activation_byte = potential_activation
                                offset += 1
                                print(f"  Detected activation function: {activation_byte}")
                        except:
                            pass
            
            # Read layer dimensions
            if offset + 8 > len(data):
                raise ValueError(f"File too short for layer {layer_idx} dimensions")
                
            inputs = struct.unpack('<I', data[offset:offset+4])[0]
            outputs = struct.unpack('<I', data[offset+4:offset+8])[0]
            offset += 8
            
            print(f"  Dimensions: {inputs} -> {outputs}")
            
            # Validate dimensions
            if inputs > 1000 or outputs > 1000:
                raise ValueError(f"Unreasonable layer size: {inputs} -> {outputs}")
            
            # Find where the next layer starts (or end of file)
            if layer_idx + 1 < num_layers:
                # Calculate expected data size for current layer
                expected_data_bytes = outputs * (4 + inputs * 4)  # bias + weights per output
                next_layer_start = offset + expected_data_bytes
                
                # Verify this points to a valid next layer
                if next_layer_start + 9 <= len(data):  # Need at least 9 bytes (1 activation + 4 inputs + 4 outputs)
                    # Check if there's an activation byte at this position
                    potential_activation = struct.unpack('<B', data[next_layer_start:next_layer_start+1])[0]
                    if 0 <= potential_activation <= 6:
                        # Try reading layer dimensions after activation byte
                        try:
                            test_inputs = struct.unpack('<I', data[next_layer_start+1:next_layer_start+5])[0]
                            test_outputs = struct.unpack('<I', data[next_layer_start+5:next_layer_start+9])[0]
                            if (1 <= test_inputs <= 100) and (1 <= test_outputs <= 100):
                                # This looks like a valid next layer with activation byte
                                available_bytes = expected_data_bytes
                                print(f"  Next layer found at {next_layer_start} (with activation)")
                            else:
                                # No activation byte, try direct layer dimensions
                                test_inputs = struct.unpack('<I', data[next_layer_start:next_layer_start+4])[0]
                                test_outputs = struct.unpack('<I', data[next_layer_start+4:next_layer_start+8])[0]
                                if (1 <= test_inputs <= 100) and (1 <= test_outputs <= 100):
                                    available_bytes = expected_data_bytes
                                    print(f"  Next layer found at {next_layer_start} (no activation)")
                                else:
                                    available_bytes = len(data) - offset
                                    print(f"  Could not verify next layer, using remaining data")
                        except:
                            available_bytes = len(data) - offset
                            print(f"  Error checking next layer, using remaining data")
                    else:
                        # No activation byte, check direct layer dimensions
                        try:
                            test_inputs = struct.unpack('<I', data[next_layer_start:next_layer_start+4])[0]
                            test_outputs = struct.unpack('<I', data[next_layer_start+4:next_layer_start+8])[0]
                            if (1 <= test_inputs <= 100) and (1 <= test_outputs <= 100):
                                available_bytes = expected_data_bytes
                                print(f"  Next layer found at {next_layer_start} (no activation)")
                            else:
                                available_bytes = len(data) - offset
                                print(f"  Could not verify next layer, using remaining data")
                        except:
                            available_bytes = len(data) - offset
                            print(f"  Error checking next layer, using remaining data")
                else:
                    # Not enough data for next layer header
                    available_bytes = len(data) - offset
                    print(f"  Using remaining data (not enough for next layer header)")
            else:
                # Last layer, use remaining bytes
                available_bytes = len(data) - offset
            
            available_floats = available_bytes // 4
            print(f"  Available data: {available_bytes} bytes = {available_floats} floats")
            
            # Calculate what we can read
            values_per_output = 1 + inputs  # 1 bias + inputs weights
            actual_outputs = available_floats // values_per_output
            
            print(f"  Expected: {outputs} outputs × {values_per_output} values = {outputs * values_per_output} floats")
            print(f"  Available: {available_floats} floats")
            print(f"  Can read: {actual_outputs} complete outputs")
            
            # Initialize arrays
            weights = np.zeros((outputs, inputs), dtype=np.float32)
            biases = np.zeros(outputs, dtype=np.float32)
            
            # Read the available data (but don't exceed declared outputs)
            actual_outputs = min(actual_outputs, outputs)
            for j in range(actual_outputs):
                # Read bias for this output neuron
                if offset + 4 > len(data):
                    break
                biases[j] = struct.unpack('<f', data[offset:offset+4])[0]
                offset += 4
                
                # Read weights from all inputs to this output neuron
                for k in range(inputs):
                    if offset + 4 > len(data):
                        break
                    weights[j, k] = struct.unpack('<f', data[offset:offset+4])[0]
                    offset += 4
            
            # For missing outputs, we keep the zero initialization
            if actual_outputs < outputs:
                print(f"  WARNING: Only read {actual_outputs}/{outputs} outputs - remaining initialized to zero")
            
            print(f"  Weights shape: {weights.shape}")
            print(f"  Weights range: {weights.min():.4f} to {weights.max():.4f}")
            print(f"  Biases shape: {biases.shape}")
            print(f"  Biases range: {biases.min():.4f} to {biases.max():.4f}")
            print(f"  Layer data ended at offset: {offset}")
            
            # Map activation byte to string
            activation_names = {
                0: 'sigmoid',
                1: 'tanh', 
                2: 'relu',
                3: 'leakyrelu',
                4: 'elu',
                5: 'selu',
                6: 'softmax'
            }
            activation_name = activation_names.get(activation_byte, 'relu')
            
            layers.append({
                'inputs': inputs,
                'outputs': outputs,
                'actual_outputs': actual_outputs,
                'weights': weights,
                'biases': biases,
                'activation': activation_name,
                'activation_byte': activation_byte
            })
        
        print(f"\nTotal bytes read: {offset}/{len(data)}")
        
        if offset != len(data):
            print(f"WARNING: {len(data) - offset} bytes remaining in file")
        else:
            print("✅ File read completely!")
        
        return {
            'layers': layers,
            'num_layers': num_layers
        }
        
    except Exception as e:
        print(f"Error reading neural network file: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Test with the original ESP32 file
    filepath = "/home/shirkit/Projects/Github/atlantico-server/weights/2025-06-14_14-32-00/0/esp17.nn"
    
    network = read_nn_binary_with_activation(filepath)
    
    if network:
        print("\n" + "="*60)
        print("🎉 SUCCESS: Neural network loaded!")
        print(f"Architecture: {' -> '.join(str(layer['inputs']) for layer in network['layers'])} -> {network['layers'][-1]['outputs']}")
        
        # Show layer details
        for i, layer in enumerate(network['layers']):
            act_info = f" (activation: {layer['activation']})" if layer['activation_byte'] is not None else " (no activation byte)"
            print(f"   Layer {i}: {layer['inputs']} -> {layer['outputs']} (read {layer['actual_outputs']} outputs){act_info}")
    else:
        print("❌ Failed to read neural network")
