"""Federated Learning Control View"""

from textual.widgets import Static, Button, Label, Input, ProgressBar
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.reactive import reactive
import threading


class ConfigurationPanel(Container):
    """Panel for training configuration"""
    
    def __init__(self, server=None):
        super().__init__()
        self.server = server
    
    def compose(self):
        yield Label("⚙️ Training Configuration", classes="panel-title")
        yield Horizontal(
            Label("Rounds:", classes="config-label"),
            Input(value="10", placeholder="Number of rounds", id="input-rounds", classes="config-input"),
        )
        yield Horizontal(
            Label("Epochs:", classes="config-label"),
            Input(value="5", placeholder="Epochs per device", id="input-epochs", classes="config-input"),
        )
        yield Horizontal(
            Label("Clients:", classes="config-label"),
            Input(value="4", placeholder="Number of devices", id="input-clients", classes="config-input"),
        )
        yield Horizontal(
            Label("Batch:", classes="config-label"),
            Input(value="batch-config/batch.json", placeholder="Path", id="input-batch", classes="config-input"),
        )


class TrainingControlPanel(Container):
    """Panel for training control buttons"""
    
    is_training = reactive(False)
    is_paused = reactive(False)
    
    def __init__(self, server=None):
        super().__init__()
        self.server = server
    
    def compose(self):
        yield Label("🎮 Training Controls", classes="panel-title")
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
        super().__init__()
        self.server = server
    
    def compose(self):
        yield Label("📊 Training Progress", classes="panel-title")
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
        
        if self.max_rounds > 0 and self.current_round > 0:
            status_widget.update(f"Round {self.current_round} of {self.max_rounds}")
            progress_percent = int((self.current_round / self.max_rounds) * 100)
            progress_bar.update(progress=progress_percent)
        else:
            status_widget.update("Not started")
            progress_bar.update(progress=0)
        
        # Device progress
        connected = len(state.connected_clients)
        device_widget.update(f"Connected Devices: {connected}")
        
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
        super().__init__()
        self.server = server
    
    def compose(self):
        yield Label("📈 Metrics", classes="panel-title")
        yield Static("No metrics yet", id="metrics-display")
    
    def update_metrics(self, accuracy: float = 0.0, loss: float = 0.0):
        """Update displayed metrics"""
        metrics_widget = self.query_one("#metrics-display", Static)
        metrics_widget.update(
            f"Global Accuracy: {accuracy:.2%}\n"
            f"Global Loss: {loss:.4f}"
        )


class FederatedView(Vertical):
    """Federated learning control view"""
    
    CSS = """
    FederatedView {
        layout: vertical;
        padding: 1;
        overflow-y: auto;
    }
    
    .view-title {
        text-style: bold;
        background: $boost;
        padding: 1;
        margin-bottom: 1;
        height: 3;
    }
    
    .panel-title {
        text-style: bold;
        background: $boost;
        padding: 1;
        height: 3;
    }
    
    .config-label {
        width: 12;
        height: 3;
        content-align: center left;
    }
    
    .config-input {
        width: 1fr;
        height: 3;
    }
    
    ConfigurationPanel Horizontal {
        height: 3;
        width: 100%;
    }
    
    .control-buttons {
        height: auto;
        padding: 1;
    }
    
    ConfigurationPanel {
        height: 16;
        max-height: 16;
        border: solid blue;
        margin-bottom: 1;
        overflow: hidden;
    }
    
    TrainingControlPanel {
        height: 6;
        max-height: 6;
        border: solid green;
        margin-bottom: 1;
        overflow: hidden;
    }
    
    ProgressPanel {
        height: 11;
        max-height: 11;
        border: solid yellow;
        margin-bottom: 1;
        overflow: hidden;
    }
    
    MetricsPanel {
        height: 5;
        max-height: 5;
        border: solid magenta;
        overflow: hidden;
    }
    """
    
    def __init__(self, server=None, **kwargs):
        super().__init__(**kwargs)
        self.server = server
        self.config_panel = None
        self.control_panel = None
        self.progress_panel = None
        self.metrics_panel = None
    
    def compose(self):
        """Create view layout"""
        yield Label("🤝 Federated Learning Control", classes="view-title")
        
        self.config_panel = ConfigurationPanel(self.server)
        self.control_panel = TrainingControlPanel(self.server)
        self.progress_panel = ProgressPanel(self.server)
        self.metrics_panel = MetricsPanel(self.server)
        
        yield self.config_panel
        yield self.control_panel
        yield self.progress_panel
        yield self.metrics_panel
    
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
            self._log_message("🛑 Stop solicitado - aguardando conclusão da rodada atual...")
    
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
