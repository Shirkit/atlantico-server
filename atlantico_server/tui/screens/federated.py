"""Federated Learning Control Screen"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Button, Label, Input, ProgressBar, Header
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.reactive import reactive
import threading, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from atlantico_server.tui.app import CustomFooter


class ConfigurationPanel(Container):
    """Panel for training configuration"""
    
    def __init__(self, server=None, config=None):
        super().__init__(classes="panel")
        self.server = server
        self.config = config or {}
        self.border_title = "Training Configuration"
    
    def compose(self):
        yield Horizontal(
            Label("Rounds:", classes="config-label"),
            Input(value=self.config.get("rounds"), placeholder="Number of rounds", id="input-rounds", classes="config-input"),
        )
        yield Horizontal(
            Label("Epochs:", classes="config-label"),
            Input(value=self.config.get("epochs"), placeholder="Epochs per device", id="input-epochs", classes="config-input"),
        )
        yield Horizontal(
            Label("Clients:", classes="config-label"),
            Input(value=self.config.get("clients"), placeholder="Number of devices", id="input-clients", classes="config-input"),
        )
        yield Horizontal(
            Label("Batch:", classes="config-label"),
            Input(value=self.config.get("batch"), placeholder="Path", id="input-batch", classes="config-input"),
        )


class TrainingControlPanel(Container):
    """Panel for training control buttons"""
    
    is_training = reactive(False)
    is_paused = reactive(False)
    
    def __init__(self, server=None):
        super().__init__(classes="panel")
        self.server = server
        self.border_title = "Training Controls"
    
    def compose(self):
        yield Horizontal(
            Button("▶ Start Training", id="btn-start-training", variant="success"),
            Button("⏹ Stop", id="btn-stop-training", variant="error", disabled=True),
            Button("⏸ Pause", id="btn-pause-training", variant="warning", disabled=True),
            classes="control-buttons"
        )
    
    def set_training_state(self, is_training: bool, is_paused: bool = False):
        """Update button states based on training status"""
        self.is_training = is_training
        self.is_paused = is_paused
        start_btn = self.query_one("#btn-start-training", Button)
        stop_btn = self.query_one("#btn-stop-training", Button)
        pause_btn = self.query_one("#btn-pause-training", Button)
        
        start_btn.disabled = is_training
        stop_btn.disabled = not is_training
        pause_btn.disabled = not is_training
        
        # Update pause button label
        if is_paused:
            pause_btn.label = "▶️ Resume"
            pause_btn.variant = "success"
        else:
            pause_btn.label = "⏸ Pause"
            pause_btn.variant = "warning"


class ProgressPanel(Container):
    """Panel showing training progress"""
    
    current_round = reactive(0)
    max_rounds = reactive(10)
    devices_completed = reactive(0)
    total_devices = reactive(0)
    
    def __init__(self, server=None):
        super().__init__(classes="panel")
        self.server = server
        self.border_title = "Training Progress"
    
    def compose(self):
        yield Static("Not started", id="progress-status")
        yield ProgressBar(total=100, show_eta=False, id="round-progress")
        yield Static("Devices: 0/0 completed", id="device-progress")
        yield Static("Status: Idle", id="training-status")
    
    def on_mount(self):
        """Setup auto-refresh"""
        self.set_interval(1.0, self.refresh_progress)
    
    def refresh_progress(self):
        """Update progress display from server state"""
        if not self.server:
            return
        
        state = self.server.state
        self.current_round = state.current_round
        self.max_rounds = state.max_rounds if state.max_rounds > 0 else 10
        
        # Update text widgets
        status_widget = self.query_one("#progress-status", Static)
        device_widget = self.query_one("#device-progress", Static)
        training_widget = self.query_one("#training-status", Static)
        progress_bar = self.query_one("#round-progress", ProgressBar)
        
        connected = len(state.connected_clients)
        if self.max_rounds > 0 and self.current_round > 0:
            status_widget.update(f"Round {self.current_round} of {self.max_rounds}")
            progress_percent = int((self.current_round / self.max_rounds) * 100)
            progress_bar.update(progress=progress_percent)
            connected = len(state.federated_clients)
        else:
            status_widget.update("Not started")
            progress_bar.update(progress=0)
        
        device_widget.update(f"Connected Devices: {connected}")
        
        # Device progress
        
        # Training status
        if state.is_federated:
            if state.is_paused:
                training_widget.update("Status: ⏸️ Paused (aggregating)")
            else:
                training_widget.update("Status: 🔄 Training in progress...")
        else:
            training_widget.update("Status: ⏸ Idle")


class MetricsPanel(Container):
    """Panel showing training metrics"""
    
    def __init__(self, server=None):
        super().__init__(classes="panel")
        self.server = server
        self.border_title = "Metrics"
    
    def compose(self):
        yield Static("No metrics yet", id="metrics-display")
    
    def update_metrics(self, accuracy: float = 0.0, loss: float = 0.0):
        """Update displayed metrics"""
        metrics_widget = self.query_one("#metrics-display", Static)
        metrics_widget.update(
            f"Global Accuracy: {accuracy:.2%}\n"
            f"Global Loss: {loss:.4f}"
        )


class FederatedScreen(Screen):
    """Federated learning screen"""
    
    AUTO_FOCUS = False
    
    def __init__(self, server=None, config=None):
        super().__init__()
        self.server = server
        self.config = config or {}
        self.config_panel = None
        self.control_panel = None
        self.progress_panel = None
        self.metrics_panel = None
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        self.config_panel = ConfigurationPanel(self.server, self.config)
        self.control_panel = TrainingControlPanel(self.server)
        self.progress_panel = ProgressPanel(self.server)
        self.metrics_panel = MetricsPanel(self.server)
        
        yield self.config_panel
        yield self.control_panel
        yield self.progress_panel
        yield self.metrics_panel
        
        footer = CustomFooter(id="custom-footer")
        footer.current_view = "federated"
        yield footer
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Save config values as they change"""
        if event.input.id == "input-rounds":
            self.config["rounds"] = event.value
        elif event.input.id == "input-epochs":
            self.config["epochs"] = event.value
        elif event.input.id == "input-clients":
            self.config["clients"] = event.value
        elif event.input.id == "input-batch":
            self.config["batch"] = event.value
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "btn-start-training":
            self.start_training()
        elif event.button.id == "btn-stop-training":
            self.stop_training()
        elif event.button.id == "btn-pause-training":
            self.pause_training()
    
    def start_training(self):
        """Start federated learning with configured parameters"""
        if not self.server:
            return
        
        # Get configuration values
        try:
            rounds_input = self.query_one("#input-rounds", Input)
            epochs_input = self.query_one("#input-epochs", Input)
            clients_input = self.query_one("#input-clients", Input)
            batch_input = self.query_one("#input-batch", Input)
            
            rounds = int(rounds_input.value) if rounds_input.value else 10
            epochs = int(epochs_input.value) if epochs_input.value else 5
            clients = int(clients_input.value) if clients_input.value else 4
            batch_file = batch_input.value if batch_input.value else None
            
        except ValueError:
            # Invalid input - could show error message
            return
        
        # Update button states
        self.control_panel.set_training_state(True)
        
        # Run training in background thread
        def run_training():
            try:
                if batch_file:
                    self.server.start_batch_federated_learning(batch_file, expected_clients=clients)
                else:
                    self.server.start_federated_learning(max_rounds=rounds, expected_clients=clients)
            except Exception as e:
                import traceback
                traceback.print_exc()
            finally:
                # Reset button states when done
                self.app.call_from_thread(self.control_panel.set_training_state, False)
        
        thread = threading.Thread(target=run_training, daemon=True)
        thread.start()
    
    def stop_training(self):
        """Stop training (graceful shutdown)"""
        if not self.server:
            return
        
        # Request graceful stop
        if self.server.stop_federated_learning():
            # Button states will be updated by the training thread when it finishes
            self._log_message("🛑 Stop requested - waiting for current round to complete...")
    
    def _log_message(self, message: str):
        """Helper to log messages (if logger available)"""
        try:
            from atlantico_server.logging import get_logger
            logger = get_logger(__name__)
            logger.info(message)
        except:
            pass
    
    def pause_training(self):
        """Pause/resume training"""
        if not self.server:
            return
        
        # Check current pause state
        if self.server.state.is_paused:
            # Resume
            if self.server.resume_federated_learning():
                self.control_panel.set_training_state(True, is_paused=False)
        else:
            # Pause
            if self.server.pause_federated_learning():
                self.control_panel.set_training_state(True, is_paused=True)



