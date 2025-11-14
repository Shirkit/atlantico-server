"""Dashboard View"""

from textual.widgets import Static, Button, Label, RichLog
from textual.containers import Container, Vertical, Horizontal
from textual.reactive import reactive
import os


class ServerStatusPanel(Container):
    """Panel showing server connection status"""
    
    is_connected = reactive(False)
    device_count = reactive(0)
    current_round = reactive(0)
    max_rounds = reactive(0)
    
    def __init__(self, server=None):
        super().__init__()
        self.server = server
    
    def compose(self):
        yield Label("📊 Server Status", classes="panel-title")
        yield Container(
            Static(id="connection-status"),
            Static(id="device-count"),
            Static(id="round-info"),
            classes="status-content"
        )
    
    def on_mount(self):
        """Update status when mounted"""
        self.update_status()
        self.set_interval(1.0, self.update_status)
    
    def update_status(self):
        """Update status display"""
        if self.server and self.server.client.is_connected():
            self.is_connected = True
            self.device_count = len(self.server.state.connected_clients)
            self.current_round = self.server.state.current_round
            self.max_rounds = self.server.state.max_rounds
        else:
            self.is_connected = False
        
        self.refresh_display()
    
    def refresh_display(self):
        """Refresh the status text"""
        conn_widget = self.query_one("#connection-status", Static)
        device_widget = self.query_one("#device-count", Static)
        round_widget = self.query_one("#round-info", Static)
        
        if self.is_connected:
            conn_widget.update("● Connected to MQTT Broker")
            conn_widget.styles.color = "green"
        else:
            conn_widget.update("○ Disconnected (Offline Mode)")
            conn_widget.styles.color = "red"
        
        device_widget.update(f"Connected Devices: {self.device_count}")
        
        if self.max_rounds > 0:
            round_widget.update(f"Training Round: {self.current_round}/{self.max_rounds}")
        else:
            round_widget.update("Training Round: Not started")


class QuickActionsPanel(Container):
    """Panel with quick action buttons"""
    
    def __init__(self, server=None):
        super().__init__()
        self.server = server
    
    def compose(self):
        yield Label("⚡ Quick Actions", classes="panel-title")
        yield Horizontal(
            Button("Check Devices", id="btn-check-devices", variant="primary"),
            Button("View Logs", id="btn-view-logs", variant="default"),
            # TODO: TEMPORARY - Remove this button after testing federated process
            Button("Start Test FL (2 rounds)", id="btn-start-federated-test", variant="warning"),
            classes="actions-row"
        )


class ActivityFeedPanel(Container):
    """Panel showing recent activity - reads last 10 lines from log file"""
    
    def __init__(self, log_file="run/logs/server.log"):
        super().__init__()
        self.log_file = log_file
        self.max_lines = 10
        self.last_line_count = 0
    
    def compose(self):
        yield Label("📋 Recent Activity", classes="panel-title")
        yield RichLog(id="activity-log", highlight=True, markup=True)
    
    def on_mount(self):
        """Setup auto-refresh"""
        self.set_interval(0.5, self.refresh_feed)
        self.refresh_feed()
    
    def refresh_feed(self):
        """Refresh by reading last 10 lines from log file"""
        log_widget = self.query_one("#activity-log", RichLog)
        
        if not os.path.exists(self.log_file):
            if self.last_line_count == 0:
                log_widget.write("Waiting for activity...")
                self.last_line_count = -1
            return
        
        try:
            with open(self.log_file, 'r') as f:
                # Read all lines and get last 10
                lines = f.readlines()
                current_count = len(lines)
                
                # Only update if line count changed
                if current_count != self.last_line_count:
                    log_widget.clear()
                    last_lines = lines[-self.max_lines:] if lines else []
                    
                    if last_lines:
                        for line in last_lines:
                            log_widget.write(line.rstrip())
                    else:
                        log_widget.write("Waiting for activity...")
                    
                    self.last_line_count = current_count
        except Exception as e:
            if self.last_line_count >= 0:
                log_widget.clear()
                log_widget.write(f"Error reading logs: {e}")
                self.last_line_count = -1


class DashboardView(Vertical):
    """Main dashboard view"""
    
    CSS = """
    DashboardView {
        layout: vertical;
        padding: 1;
    }
    
    .panel-title {
        text-style: bold;
        background: $boost;
        padding: 1;
        margin-bottom: 1;
    }
    
    .status-content {
        padding: 1;
        height: auto;
    }
    
    .actions-row {
        height: auto;
        padding: 1;
    }
    
    .activity-content {
        height: 10;
        border: solid green;
        padding: 1;
        overflow-y: auto;
    }
    
    ServerStatusPanel {
        height: auto;
        max-height: 8;
        border: solid blue;
        margin-bottom: 1;
    }
    
    .view-title {
        text-style: bold;
        background: $boost;
        padding: 1;
        margin-bottom: 1;
    }
    
    QuickActionsPanel {
        height: 6;
        border: solid yellow;
        margin-bottom: 1;
    }
    
    ActivityFeedPanel {
        height: 15;
        border: solid magenta;
    }
    """
    
    def __init__(self, server=None, **kwargs):
        super().__init__(**kwargs)
        self.server = server
        self.activity_feed = None
    
    def compose(self):
        """Create view layout"""
        # yield ServerStatusPanel(self.server)
        # TODO: TEMPORARY - Simplified for testing. ServerStatusPanel removed because it was blocking other widgets.
        yield Label("Atlantico Federated Learning Server", classes="view-title")
        yield Static(f"Connected Devices: {len(self.server.state.connected_clients) if self.server else 0}")
        yield Label("⚡ Test Federated Learning", classes="view-title")
        yield Button("▶ Start Test FL (2 rounds)", id="btn-start-federated-test", variant="warning")
        self.activity_feed = ActivityFeedPanel()
        yield self.activity_feed
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "btn-check-devices":
            self.app.action_show_devices()
        elif event.button.id == "btn-view-logs":
            self.app.action_show_logs()
        elif event.button.id == "btn-start-federated-test":
            self.start_test_federated_learning()
    
    def start_test_federated_learning(self):
        """Temporary function to test federated learning from TUI"""
        import threading
        
        if not self.server:
            return
        
        # Get connected devices
        num_devices = len(self.server.state.connected_clients)
        if num_devices == 0:
            return
        
        # Run federated learning in background thread so TUI doesn't freeze
        def run_federated():
            try:
                self.server.start_federated_learning(max_rounds=2, expected_clients=num_devices)
            except Exception as e:
                import traceback
                traceback.print_exc()
        
        thread = threading.Thread(target=run_federated, daemon=True)
        thread.start()
