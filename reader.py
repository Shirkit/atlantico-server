import struct
import numpy as np
from typing import Optional, List, BinaryIO

class NeuralNetworkLoader:
    def __init__(self):
        self.numberOflayers = 0
        self.layers = []
        self.ActFunctionPerLayer = None
        
    def load_from_file(self, filepath: str) -> bool:
        """Load neural network from binary file"""
        try:
            with open(filepath, 'rb') as file:
                return self.load_from_stream(file)
        except Exception as e:
            print(f"Error loading file {filepath}: {e}")
            return False
    
    def load_from_stream(self, file: BinaryIO) -> bool:
        """Load neural network from binary stream"""
        try:
            # Read number of layers
            layers_data = file.read(4)
            if len(layers_data) < 4:
                return False
            self.numberOflayers = struct.unpack('<I', layers_data)[0]
            
            # Initialize layers list and activation functions
            self.layers = []
            self.ActFunctionPerLayer = np.zeros(self.numberOflayers, dtype=np.uint8)
            
            for i in range(self.numberOflayers):
                layer_info = {}
                
                # Read activation function for this layer (ACTIVATION__PER_LAYER is defined)
                actfunc_data = file.read(1)
                if len(actfunc_data) < 1:
                    return False
                self.ActFunctionPerLayer[i] = struct.unpack('<B', actfunc_data)[0]
                
                # Read layer inputs and outputs
                inputs_data = file.read(4)
                outputs_data = file.read(4)
                if len(inputs_data) < 4 or len(outputs_data) < 4:
                    return False
                
                tmp_layerInputs = struct.unpack('<I', inputs_data)[0]
                tmp_layerOutputs = struct.unpack('<I', outputs_data)[0]
                
                layer_info['inputs'] = tmp_layerInputs
                layer_info['outputs'] = tmp_layerOutputs
                layer_info['activation_function'] = self.ActFunctionPerLayer[i]
                
                # Since NO_BIAS is undefined and MULTIPLE_BIASES_PER_LAYER is defined,
                # we have multiple biases (one per output neuron)
                biases = []
                weights = []
                
                # Read weights and biases for each output neuron
                for j in range(tmp_layerOutputs):
                    # Read bias for this output neuron (MULTIPLE_BIASES_PER_LAYER)
                    bias_data = file.read(4)  # sizeof(float) = 4 bytes
                    if len(bias_data) < 4:
                        return False
                    bias_value = struct.unpack('<f', bias_data)[0]
                    biases.append(bias_value)
                    
                    # Read weights for this output neuron
                    neuron_weights = []
                    for k in range(tmp_layerInputs):
                        weight_data = file.read(4)  # sizeof(float) = 4 bytes
                        if len(weight_data) < 4:
                            return False
                        weight_value = struct.unpack('<f', weight_data)[0]
                        neuron_weights.append(weight_value)
                    
                    weights.append(neuron_weights)
                
                # Store layer information
                layer_info['biases'] = np.array(biases, dtype=np.float32)
                layer_info['weights'] = np.array(weights, dtype=np.float32)  # Shape: [outputs, inputs]
                
                self.layers.append(layer_info)
            
            return True
            
        except Exception as e:
            print(f"Error loading neural network: {e}")
            return False
    
    def get_layer_info(self, layer_index: int) -> Optional[dict]:
        """Get information about a specific layer"""
        if 0 <= layer_index < len(self.layers):
            return self.layers[layer_index]
        return None
    
    def get_weights_matrix(self, layer_index: int) -> Optional[np.ndarray]:
        """Get weights as a 2D numpy array for a specific layer"""
        if 0 <= layer_index < len(self.layers):
            return self.layers[layer_index]['weights']
        return None
    
    def get_biases(self, layer_index: int) -> Optional[np.ndarray]:
        """Get biases for a specific layer"""
        if 0 <= layer_index < len(self.layers):
            return self.layers[layer_index]['biases']
        return None
    
    def get_activation_function(self, layer_index: int) -> Optional[int]:
        """Get activation function index for a specific layer"""
        if 0 <= layer_index < len(self.layers):
            return self.layers[layer_index]['activation_function']
        return None
    
    def print_network_info(self):
        """Print information about the loaded network"""
        print(f"Neural Network with {self.numberOflayers} layers:")
        print("-" * 60)
        
        for i, layer in enumerate(self.layers):
            print(f"Layer {i+1}:")
            print(f"  Architecture: {layer['inputs']} inputs -> {layer['outputs']} outputs")
            print(f"  Activation function: {layer['activation_function']}")
            print(f"  Weights shape: {layer['weights'].shape}")
            print(f"  Biases shape: {layer['biases'].shape}")
            
            # Print sample weights and biases
            print(f"  Sample biases: {layer['biases'][:min(3, len(layer['biases']))]}")
            print(f"  Sample weights (first neuron): {layer['weights'][0, :min(5, layer['weights'].shape[1])]}")
            print("-" * 40)

# Convenience function
def load_neural_network(filepath: str) -> Optional[NeuralNetworkLoader]:
    """Convenience function to load a neural network from file"""
    loader = NeuralNetworkLoader()
    if loader.load_from_file(filepath):
        return loader
    return None

# Example usage:
if __name__ == "__main__":
    # Load the neural network
    nn = load_neural_network("/home/shirkit/Projects/Github/atlantico-server/weights/2025-06-11_00-01-23/0/esp01.nn")
    
    if nn:
        # Print network information

        print(nn.layers[0])
        print("")
        nn.print_network_info()
        
        # Access specific layer data
        for i in range(nn.numberOflayers):
            weights = nn.get_weights_matrix(i)
            biases = nn.get_biases(i)
            activation_func = nn.get_activation_function(i)
            
            print(f"\nLayer {i+1} Details:")
            print(f"  Weights shape: {weights.shape}")
            print(f"  Biases shape: {biases.shape}")
            print(f"  Activation function: {activation_func}")
            
            # You can now use these arrays with any ML framework
            # like TensorFlow, PyTorch, etc.
    else:
        print("Failed to load neural network")