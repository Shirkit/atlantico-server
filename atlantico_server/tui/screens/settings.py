"""Settings Screen"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Header, Switch, Button, Checkbox
from textual.containers import Container, Vertical, Horizontal
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from atlantico_server.tui.app import CustomFooter


class SettingsScreen(Screen):
    """Settings screen"""
    
    AUTO_FOCUS = False
    
    def __init__(self, server=None):
        super().__init__()
        self.server = server
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        container = Vertical(
            # Log Settings Panel
            Checkbox("Show Date in Logs", value=self.app.display_config["show_date"], id="switch-show-date"),
            Button("Clear Logs", id="btn-clear-logs", variant="error"),
            classes="panel"
        )
        container.border_title = "Logs Configuration"
        yield container

        footer = CustomFooter(id="custom-footer")
        footer.current_view = "settings"
        yield footer
            
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "btn-clear-logs":
            self.clear_logs()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes"""
        if event.checkbox.id == "switch-show-date":
            self.app.display_config["show_date"] = event.value
            self.app._save_config()
            
    def clear_logs(self):
        """Clear the log file"""
        log_file = os.environ.get('ATLANTICO_SERVER_LOG', 'run/logs/server.log')
        try:
            with open(log_file, "w") as f:
                f.write("")
        except Exception:
            pass
