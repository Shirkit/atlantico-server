"""Main TUI Application"""

import json
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Container
from textual.binding import Binding
from textual.reactive import reactive
from textual.screen import Screen
from atlantico_server.server import (
    TOPIC_SEND_COMMANDS_TO_DEVICES,
    TOPIC_RECEIVE_COMMANDS_FROM_DEVICES
)


class CustomFooter(Container):
    """Custom footer that highlights the current view"""
    
    current_view = reactive("dashboard")
    
    def compose(self) -> ComposeResult:
        yield Static(id="footer-content")
    
    def on_mount(self) -> None:
        self.update_footer()
    
    def watch_current_view(self, view: str) -> None:
        """Update footer when view changes"""
        if self.is_mounted:
            self.update_footer()
    
    def update_footer(self) -> None:
        """Update the footer text"""
        views = {
            "dashboard": ("d", "Dashboard"),
            "devices": ("v", "Devices"), 
            "federated": ("f", "Federate"),
            "logs": ("l", "Logs"),
            "settings": ("s", "Settings")
        }
        
        parts = []
        for view_id, (key, label) in views.items():
            if view_id == self.current_view:
                parts.append(f"[bold white]\\[{key}] {label}[/bold white]")
            else:
                parts.append(f"\\[{key}] {label}")
        
        footer_text = "  ".join(parts) + "    \\[q] Quit"
        footer_widget = self.query_one("#footer-content", Static)
        footer_widget.update(footer_text)


class BaseScreen(Screen):
    """Base screen with header and footer"""
    
    def __init__(self, server=None, current_view="dashboard"):
        super().__init__()
        self.server = server
        self.current_view = current_view
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield CustomFooter(id="custom-footer")


class ServerApp(App):
    """Atlantico Federated Learning Server TUI"""
    
    CSS_PATH = "styles/main.tcss"
    
    ENABLE_COMMAND_PALETTE = False
    
    def watch_css(self) -> bool:
        return True
    
    BINDINGS = [
        Binding("d", "show_dashboard", "Dashboard"),
        Binding("v", "show_devices", "Devices"),
        Binding("f", "show_federated", "Federate"),
        Binding("l", "show_logs", "Logs"),
        Binding("s", "show_settings", "Settings"),
        Binding("q", "quit", "Quit", priority=True),
    ]
    
    def __init__(self, server=None):
        super().__init__()
        self.server = server
        self.title = "Atlantico Federated Learning Server"
        self.sub_title = ""
        
        # Store federated learning config values
        self.federated_config = {
            "rounds": "10",
            "epochs": "5",
            "clients": "4",
            "batch": "batch-config/batch.json"
        }
        
        self._screens_installed = False
    
    def on_mount(self) -> None:
        """Called when app is mounted"""
        self._install_screens()
        self.push_screen("dashboard")
        self.update_header("Dashboard")
        
        # Set up alive check if server is connected
        if self.server and self.server.client.is_connected():
            self.server.client.subscribe([(TOPIC_RECEIVE_COMMANDS_FROM_DEVICES, 0)])
            self.alive_check_cycle()
            self.set_interval(30.0, self.alive_check_cycle)
    
    def _install_screens(self) -> None:
        """Install all screens once for fast switching"""
        if self._screens_installed:
            return
        
        from .screens.dashboard import DashboardScreen
        from .screens.devices import DevicesScreen
        from .screens.federated import FederatedScreen
        from .screens.logs import LogsScreen
        from .screens.settings import SettingsScreen
        
        self.install_screen(DashboardScreen(self.server), name="dashboard")
        self.install_screen(DevicesScreen(self.server), name="devices")
        self.install_screen(FederatedScreen(self.server, self.federated_config), name="federated")
        self.install_screen(LogsScreen(self.server), name="logs")
        self.install_screen(SettingsScreen(self.server), name="settings")
        
        self._screens_installed = True
    
    def alive_check_cycle(self) -> None:
        """Complete alive check cycle: send alive command to devices"""
        if not self.server or not self.server.client.is_connected():
            return
        
        alive_command = {"command": "alive"}
        command_json = json.dumps(alive_command, separators=(',', ':'))
        self.server.client.publish(TOPIC_SEND_COMMANDS_TO_DEVICES, command_json)
    
    def update_header(self, screen_name: str) -> None:
        """Update header with screen name"""
        self.title = f"{screen_name} • AILA Federated Framework"
    
    def action_show_dashboard(self) -> None:
        self.switch_screen("dashboard")
        self.update_header("Dashboard")
    
    def action_show_devices(self) -> None:
        self.switch_screen("devices")
        self.update_header("Devices")
    
    def action_show_federated(self) -> None:
        self.switch_screen("federated")
        self.update_header("Federated Learning")
    
    def action_show_logs(self) -> None:
        self.switch_screen("logs")
        self.update_header("Logs")
    
    def action_show_settings(self) -> None:
        self.switch_screen("settings")
        self.update_header("Settings")
