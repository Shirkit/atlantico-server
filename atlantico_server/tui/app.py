"""Main TUI Application"""

import json
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, ContentSwitcher
from textual.containers import Container
from textual.binding import Binding
from atlantico_server.server import (
    TOPIC_SEND_COMMANDS_TO_DEVICES,
    TOPIC_RECEIVE_COMMANDS_FROM_DEVICES
)


class ServerApp(App):
    """Atlantico Federated Learning Server TUI"""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #content-area {
        height: 1fr;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("d", "show_dashboard", "Dashboard"),
        Binding("v", "show_devices", "Devices"),
        Binding("f", "show_federated", "Federate"),
        Binding("l", "show_logs", "Logs"),
        Binding("s", "show_settings", "Settings"),
    ]
    
    def __init__(self, server=None):
        super().__init__()
        self.server = server
        self.title = "Atlantico Federated Learning Server"
        self.sub_title = "Terminal UI"
    
    def compose(self) -> ComposeResult:
        """Create child widgets"""
        from .screens.dashboard import DashboardView
        from .screens.devices import DevicesView
        from .screens.federated import FederatedView
        from .screens.logs import LogsView
        from .screens.settings import SettingsView
        
        yield Header()
        with ContentSwitcher(initial="dashboard", id="content-area"):
            yield DashboardView(self.server, id="dashboard")
            yield DevicesView(self.server, id="devices")
            yield FederatedView(self.server, id="federated")
            yield LogsView(self.server, id="logs")
            yield SettingsView(self.server, id="settings")
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app is mounted"""
        self.action_show_dashboard()
        
        # Set up alive check if server is connected
        if self.server and self.server.client.is_connected():
            # Subscribe to command responses once
            self.server.client.subscribe([(TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)])
            
            # Start the alive check cycle
            self.alive_check_cycle()
            # Repeat every 30 seconds
            self.set_interval(30.0, self.alive_check_cycle)
    
    def alive_check_cycle(self) -> None:
        """Complete alive check cycle: clear list, send command, wait for responses"""
        if not self.server or not self.server.client.is_connected():
            return
        
        # Send alive command - devices will respond and update their last_seen timestamp
        alive_command = {"command": "alive"}
        command_json = json.dumps(alive_command, separators=(',', ':'))
        self.server.client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, command_json)
    
    def action_show_dashboard(self) -> None:
        """Show dashboard view"""
        self.query_one(ContentSwitcher).current = "dashboard"
    
    def action_show_devices(self) -> None:
        """Show devices view"""
        self.query_one(ContentSwitcher).current = "devices"
    
    def action_show_federated(self) -> None:
        """Show federated learning view"""
        self.query_one(ContentSwitcher).current = "federated"
    
    def action_show_logs(self) -> None:
        """Show logs view"""
        self.query_one(ContentSwitcher).current = "logs"
    
    def action_show_settings(self) -> None:
        """Show settings view"""
        self.query_one(ContentSwitcher).current = "settings"
