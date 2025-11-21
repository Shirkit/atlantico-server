"""Settings Screen"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Header
from textual.containers import Container, Vertical
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
        yield Container(
            Static("⚙️  Settings View", classes="view-title"),
            Static("\nConfiguration options will appear here."),
            Static("\nPress [d] for Dashboard or [q] to quit"),
        )
        footer = CustomFooter(id="custom-footer")
        footer.current_view = "settings"
        yield footer
