"""Federated Learning Control Screen"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Button, Label, Input, ProgressBar, Header, DirectoryTree
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.reactive import reactive
from typing import Iterable
from pathlib import Path
import threading, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from atlantico_server.tui.app import CustomFooter

class FilteredDirectoryTree(DirectoryTree):
    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [path for path in paths if path.is_dir() or path.name.endswith("json")]

class ConfigurationPanel(Container):
    """Panel for training configuration"""
    
    def __init__(self, server=None, config=None):
        super().__init__(classes="panel")
        self.server = server
        self.config = config or {}
        self.border_title = "Training Configuration"
    
    def compose(self):
        yield Horizontal(
            Label("Clients:", classes="config-label"),
            Input(value=self.config.get("clients"), placeholder="Number of devices", id="input-clients", classes="config-input"),
        )
        yield Horizontal(
            Label("Batch:", classes="config-label"),
            Input(value=self.config.get("batch"), placeholder="Path", id="input-batch", classes="config-input"),
        )
        yield FilteredDirectoryTree(id="batch-file-tree", classes="file-tree", path="./")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection from directory tree"""
        batch_input = self.query_one("#input-batch", Input)
        batch_input.value = str(event.path)
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
        yield Static("", id="training-status")

        yield Static("", id="test-count", classes="progress-count")
        yield ProgressBar(total=0, show_eta=False, id="test-progress", classes="progress-bar", show_percentage=False)

        yield Static("", id="round-count", classes="progress-count")
        yield ProgressBar(total=0, show_eta=False, id="round-progress", classes="progress-bar", show_percentage=False)

        yield Static("", id="client-count", classes="progress-count")
        yield ProgressBar(total=0, show_eta=False, id="client-progress", classes="progress-bar", show_percentage=False)
    
    def on_mount(self):
        """Setup auto-refresh"""
        self.refresh_progress()
        self.set_interval(1.0, self.refresh_progress)
    
    def refresh_progress(self):
        """Update progress display from server state"""
        if not self.server:
            return
        
        state = self.server.state
        
        try:
            training_widget = self.query_one("#training-status", Static)
            
            test_bar = self.query_one("#test-progress", ProgressBar)
            test_count = self.query_one("#test-count", Static)
            
            round_bar = self.query_one("#round-progress", ProgressBar)
            round_count = self.query_one("#round-count", Static)
            
            client_bar = self.query_one("#client-progress", ProgressBar)
            client_count = self.query_one("#client-count", Static)
        except Exception:
            return
            
        # Update Training Status
        if state.is_federated:
            if state.is_paused:
                training_widget.update("Status: Paused (aggregating)")
            else:
                training_widget.update("Status: Training in progress...")
        else:
            training_widget.update("Status: Not Running")
            
        # Update Test Progress
        current_test = getattr(state, 'current_test_index', 0)
        total_tests = getattr(state, 'total_tests', 0)
        test_name = getattr(state, 'current_test_name', '')
        
        if total_tests > 0:
            test_count.update(f"Tests Run: {current_test}/{total_tests} ({test_name})")
            test_bar.update(progress=current_test, total=total_tests)
        else:
            test_bar.update(progress=0)
            test_count.update("Tests Run: -/-")
            
        # Update Round Progress
        current_round = state.current_round
        max_rounds = state.max_rounds if state.max_rounds > 0 else 0
        
        if state.is_federated and max_rounds > 0:
            round_bar.update(progress=current_round, total=max_rounds)
            round_count.update(f"Rounds Completed: {current_round}/{max_rounds}")
        else:
            round_bar.update(progress=0)
            round_count.update("Rounds Completed: -/-")
            
        # Update Client Progress
        total_clients = len(state.federated_clients)
        waiting_clients = len(state.waiting_for_clients)
        completed_clients = total_clients - waiting_clients
        
        if total_clients > 0:
            client_bar.update(progress=completed_clients, total=total_clients)
            client_count.update(f"Current Round: {completed_clients}/{total_clients}")
        else:
            client_bar.update(progress=0)
            client_count.update("Current Round: -/-")


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
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        self.config_panel = ConfigurationPanel(self.server, self.config)
        self.control_panel = TrainingControlPanel(self.server)
        self.progress_panel = ProgressPanel(self.server)
        
        yield Vertical(
            self.progress_panel,
            Horizontal(
                self.config_panel,
                self.control_panel,
                classes="bottom-controls"
            ),
            classes="main-layout"
        )
        
        footer = CustomFooter(id="custom-footer")
        footer.current_view = "federated"
        yield footer
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Save config values as they change"""
        if event.input.id == "input-clients":
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
            clients_input = self.query_one("#input-clients", Input)
            batch_input = self.query_one("#input-batch", Input)
            
            clients = int(clients_input.value) if clients_input.value else None
            batch_file = batch_input.value if batch_input.value else None
            
        except ValueError:
            # Invalid input - could show error message
            return
        
        if not clients or not batch_file:
            self.app.notify("Please provide valid number of clients and batch file path.", severity="error")
            return
        
        # Update button states
        self.control_panel.set_training_state(True)
        
        # Run training in background thread
        def run_training():
            try:
                if batch_file:
                    self.server.start_batch_federated_learning(batch_file, expected_clients=clients)
                else:
                    # Default to 10 rounds if no batch file provided
                    self.server.start_federated_learning(max_rounds=10, expected_clients=clients)
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



