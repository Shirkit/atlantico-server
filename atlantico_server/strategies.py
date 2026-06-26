import os
import re
import numpy as np
from .log_setup import setup_logging

class BaseStrategy:
    """
    Base class for all strategies.
    
    Documented Events:
    - on_round_aggregation_completed: Fired when a round aggregation is finished. 
      Data: {"model_path": str, "round": int}
    - on_parent_model_received: Fired when a model is received from the parent aggregator.
      Data: {"model_path": str}
    - round_finished: Fired when a round is finished. Returns wether we can continue with processing.
      Data: {"round": int}
    """
    def __init__(self, server):
        self.server = server
        if server:
            self.logger = server.logger

    def setup(self):
        """Register event handlers"""
        pass

    def AsString(self):
        return self.__class__.__name__

    def NiceString(self):
        str = self.AsString().replace("Strategy", "").replace("_", " ")
        str = re.sub(r'(?<!^)(?=[A-Z])', ' ', str)
        return str
    
    def GetType(self):
        """Return type of strategy: process_type, merge_strategy, or aggregation_algorithm"""
        return "Base"

class SynchronousStrategy(BaseStrategy):
    """
    Process Type Strategy: Synchronous
    Waits for the parent model before proceeding with aggregation.
    """
    def setup(self):
        self.server.register_event_handler("on_parent_model_received", self.on_parent_model_received, priority=5)
        self.parent_model_received = False

    def on_parent_model_received(self, data):
        """Strategy: Proceed with aggregation after receiving parent model"""
        self.parent_model_received = True

    def round_finished(self, data):
        """Strategy: Wait for parent model before proceeding"""
        if not self.parent_model_received:
            return False
        self.parent_model_received = False
        return True
    
    def on_round_aggregation_completed(self, data):
        """Strategy: Push aggregated model to parent immediately after aggregation"""
        if self.server.hierarchical_config["enabled"]:
            self.server.push_model_to_parent(data.get("model_path"))

    def GetType(self):
        return "process_type"

class AsynchronousStrategy(BaseStrategy):
    """
    Process Type Strategy: Latest Asynchronous
    Pushes the aggregated model to the parent immediately after aggregation and does not wait for further parent model.
    """
    def setup(self):
        self.server.register_event_handler("on_round_aggregation_completed", self.on_round_aggregation_completed, priority=5)

    def on_round_aggregation_completed(self, data):
        """Strategy: Push aggregated model to parent immediately after aggregation"""
        if self.server.hierarchical_config["enabled"]:
            self.server.push_model_to_parent(data.get("model_path"))

    def GetType(self):
        return "process_type"

class BoundedAsynchronousStrategy(BaseStrategy):
    """
    Process Type Strategy: Bounded Asynchronous
    Allows asynchronous training but limits the child to being at most N rounds ahead of the parent aggregator.
    """
    def __init__(self, server):
        super().__init__(server)
        self.parent_models_received = 0

    def setup(self):
        self.server.register_event_handler("on_parent_model_received", self.on_parent_model_received, priority=5)
        self.server.register_event_handler("on_round_aggregation_completed", self.on_round_aggregation_completed, priority=5)

    def on_parent_model_received(self, data):
        self.parent_models_received += 1
        if self.logger:
            self.logger.info(f"Strategy: Bounded Asynchronous parent model received ({self.parent_models_received} total)")

    def round_finished(self, data):
        """Limit local rounds to parent_models_received + window_size"""
        local_round = data.get("round", 0)
        
        # If hierarchical mode is disabled (parent terminated or disconnected), do not wait
        if self.server and hasattr(self.server, 'hierarchical_config') and not self.server.hierarchical_config.get("enabled", False):
            return True

        window_size = 10
        if self.server and hasattr(self.server, 'hierarchical_config'):
            val = self.server.hierarchical_config.get("sliding_window")
            if val is not None and val != "":
                try:
                    window_size = int(val)
                except ValueError:
                    window_size = 10
            else:
                window_size = 10
        else:
            window_size = 10
        
        # If we are more than window_size rounds ahead of the parent, wait
        if local_round - self.parent_models_received > window_size:
            if self.logger:
                self.logger.info(f"Strategy: Bounded Asynchronous waiting (local round {local_round} is > {window_size} rounds ahead of parent)")
            return False
        return True

    def on_round_aggregation_completed(self, data):
        """Strategy: Push aggregated model to parent immediately after aggregation"""
        if self.server and hasattr(self.server, 'hierarchical_config') and self.server.hierarchical_config["enabled"]:
            self.server.push_model_to_parent(data.get("model_path"))

    def GetType(self):
        return "process_type"

class AfterRoundEndHalfWeightStrategy(BaseStrategy):
    """
    Merge Strategy: After Round End (50%)
    Merges the parent model with the aggregated model (50/50) on the end of the next round's aggregation.
    """
    def __init__(self, server):
        # FIXME: Potential race condition for missmatch data between parent_model_pending and latest_model_from_parent while receiving data, need to lock before running
        super().__init__(server)
        self.parent_model_pending = False
        self.latest_model_from_parent = None

    def setup(self):
        self.server.register_event_handler("on_parent_model_received", self.on_parent_model_received, priority=5)
        self.server.register_event_handler("on_round_aggregation_completed", self.on_round_aggregation_completed, priority=10)

    def on_parent_model_received(self, data):
        """Strategy: Mark that a parent model has been received"""
        self.logger.info("Strategy: Parent model received, pending merge on next round")
        self.parent_model_pending = True
        self.latest_model_from_parent = data.get("model_path")

    def on_round_aggregation_completed(self, data):
        """Strategy: Merge parent model with aggregated model (50/50) if pending"""
        aggregated_path = data.get("model_path")
        
        if not self.parent_model_pending or not self.latest_model_from_parent or not os.path.exists(self.latest_model_from_parent):
            # self.logger.warning(f"Strategy: Parent model not yet received or not found at {self.latest_model_from_parent}")
            return
            
        try:
            # Load both models
            aggregated_network = self.server._read_binary_nn_file(aggregated_path)
            parent_network = self.server._read_binary_nn_file(self.latest_model_from_parent)
            
            if aggregated_network is None or parent_network is None:
                self.logger.error("Failed to load models for merging")
                return
                
            # Use the configured aggregation strategy to merge (average) the two models
            merged_network = self.server.strategies.aggregate([aggregated_network, parent_network])
            
            if merged_network is None:
                self.logger.error("Failed to merge models")
                return
            
            # Save merged model back to aggregated path
            success = self.server._write_binary_nn_file(aggregated_path, merged_network)
            
            if success:
                self.logger.info("Successfully merged parent model with aggregated model")
                self.parent_model_pending = False # Reset flag
            else:
                self.logger.error("Failed to save merged model")
                
        except Exception as e:
            self.logger.error(f"Error merging models: {e}")
            import traceback
            traceback.print_exc()

    def GetType(self):
        return "merge_strategy"

class OnRoundEndAsAnotherClientStrategy(BaseStrategy):
    """
    Merge Strategy: On Round End as Another Client 
    Merges the parent model along with other client models during the current round's aggregation.
    """
    def __init__(self, server):
        # FIXME: Potential race condition for missmatch data between parent_model_pending and latest_model_from_parent while receiving data, need to lock before running
        super().__init__(server)
        self.parent_model_pending = False
        self.latest_model_from_parent = None

    def setup(self):
        self.server.register_event_handler("on_parent_model_received", self.on_parent_model_received, priority=5)
        self.server.register_event_handler("on_round_aggregation_completed", self.on_round_aggregation_completed, priority=10)

    def on_parent_model_received(self, data):
        """Strategy: Mark that a parent model has been received"""
        self.logger.info("Strategy: Parent model received, pending merge on next round")
        self.parent_model_pending = True
        self.latest_model_from_parent = data.get("model_path")

    def on_round_aggregation_started(self, data):
        """Strategy: Include parent model in current round aggregation if pending"""
        if not self.parent_model_pending or not os.path.exists(self.latest_model_from_parent):
            self.logger.warning(f"Parent model not yet received or not found at {self.latest_model_from_parent}, cannot include in aggregation")
            return data.get("files")
        
        files = data.get("files", [])
        files.append(self.latest_model_from_parent)
        self.logger.info("Strategy: Including parent model in current round aggregation")
        
        return files

    def on_round_aggregation_completed(self, data):
        """Strategy: Merge parent model with aggregated model (50/50) if pending"""
        aggregated_path = data.get("model_path")
        
        if not self.parent_model_pending or not os.path.exists(self.latest_model_from_parent):
            self.logger.warning(f"Parent model not yet received or not found at {self.latest_model_from_parent}")
            return
            
        try:
            # Load both models
            aggregated_network = self.server._read_binary_nn_file(aggregated_path)
            parent_network = self.server._read_binary_nn_file(self.latest_model_from_parent)
            
            if aggregated_network is None or parent_network is None:
                self.logger.error("Failed to load models for merging")
                return
                
            # Use the configured aggregation strategy to merge (average) the two models
            merged_network = self.server.strategies.aggregate([aggregated_network, parent_network])
            
            if merged_network is None:
                self.logger.error("Failed to merge models")
                return
            
            # Save merged model back to aggregated path
            success = self.server._write_binary_nn_file(aggregated_path, merged_network)
            
            if success:
                self.logger.info("Successfully merged parent model with aggregated model")
                self.parent_model_pending = False # Reset flag
            else:
                self.logger.error("Failed to save merged model")
                
        except Exception as e:
            self.logger.error(f"Error merging models: {e}")
            import traceback
            traceback.print_exc()

    def GetType(self):
        return "merge_strategy"

class FedAvgStrategy(BaseStrategy):
    """
    Aggregation Algorithm: FedAvg
    Standard Federated Averaging: averages weights and biases from all clients.
    """
    def aggregate(self, networks):
        """
        Aggregate a list of networks using FedAvg.
        Returns the aggregated network structure or None on error.
        """
        if not networks:
            return None
            
        # Verify all networks have the same structure
        first_network = networks[0]
        for i, network in enumerate(networks[1:], 1):
            if network['numberOflayers'] != first_network['numberOflayers']:
                self.logger.error(f"Different number of layers in network {i}")
                return None
            
            for layer_idx in range(network['numberOflayers']):
                first_layer = first_network['layers'][layer_idx]
                curr_layer = network['layers'][layer_idx]
                
                if (first_layer['inputs'] != curr_layer['inputs'] or
                    first_layer['outputs'] != curr_layer['outputs']):
                    self.logger.error(f"Different layer structure in network {i}")
                    return None
        
        # Create aggregated network structure
        aggregated_network = {
            'numberOflayers': first_network['numberOflayers'],
            'layers': []
        }
        
        # Aggregate each layer
        for layer_idx in range(first_network['numberOflayers']):
            first_layer = first_network['layers'][layer_idx]
            
            aggregated_layer = {
                'inputs': first_layer['inputs'],
                'outputs': first_layer['outputs'],
                'activation_function': first_layer['activation_function'],
                'biases': np.zeros(first_layer['outputs'], dtype=np.float32),
                'weights': np.zeros((first_layer['outputs'], first_layer['inputs']), dtype=np.float32)
            }
            
            # Collect all biases and weights for this layer across all networks
            layer_biases = [np.array(network['layers'][layer_idx]['biases']) for network in networks]
            layer_weights = [np.array(network['layers'][layer_idx]['weights']) for network in networks]
            
            # Calculate mean
            aggregated_layer['biases'] = np.mean(layer_biases, axis=0)
            aggregated_layer['weights'] = np.mean(layer_weights, axis=0)
            
            aggregated_network['layers'].append(aggregated_layer)
            
        return aggregated_network

    def GetType(self):
        return "aggregation_algorithm"

class Strategies:
    """Manager for Hierarchical Federated Learning Strategies"""
    
    def __init__(self, server):
        self.server = server
        self.active_strategies = []
        self.aggregation_strategy = None
        
    def setup(self):
        """Setup strategies based on configuration"""
        config = self.server.hierarchical_config
        self.active_strategies = []

        # register any child of BaseStrategy to the server event system
        algo = False
        merge = False
        proc = False
        for subclass in BaseStrategy.__subclasses__():
            strategy_instance = subclass(self.server)
            if strategy_instance:
                if config.get("process_type") == strategy_instance.AsString():
                    self.active_strategies.append(strategy_instance)
                    proc = True
                if config.get("merge_strategy") == strategy_instance.AsString():
                    self.active_strategies.append(strategy_instance)
                    merge = True
                if config.get("aggregation_algorithm") == strategy_instance.AsString():
                    self.aggregation_strategy = strategy_instance
                    algo = True

        if not proc:
            self.active_strategies.append(AsynchronousStrategy(self.server))
        if not merge:
            self.active_strategies.append(AfterRoundEndHalfWeightStrategy(self.server))
        if not algo:
            self.aggregation_strategy = FedAvgStrategy(self.server)

        self.server.hierarchical_config["process_type"] = self.active_strategies[0].AsString()
        self.server.hierarchical_config["merge_strategy"] = self.active_strategies[1].AsString()
        self.server.hierarchical_config["aggregation_algorithm"] = self.aggregation_strategy.AsString()

        # Setup all active strategies
        for strategy in self.active_strategies:
            strategy.setup()
            
    def aggregate(self, networks):
        """Delegate aggregation to the selected strategy"""
        if self.aggregation_strategy:
            return self.aggregation_strategy.aggregate(networks)
        return None

def GetListOfStrategies():
    """Get a list of all available strategies"""
    strategies = {
        "process_type": [],
        "merge_strategy": [],
        "aggregation_algorithm": []
    }
    for subclass in BaseStrategy.__subclasses__():
        strategy_instance = subclass(None)
        if strategy_instance:
            strategies[strategy_instance.GetType()].append((strategy_instance.NiceString(), strategy_instance.AsString()))
    return strategies