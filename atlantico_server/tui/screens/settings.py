"""Settings View"""

from textual.widgets import Static
from textual.containers import Container, Vertical


class SettingsView(Vertical):
    """Settings configuration view"""
    
    def __init__(self, server=None, **kwargs):
        super().__init__(**kwargs)
        self.server = server
    
    def compose(self):
        """Create view layout"""
        yield Container(
            Static("⚙️  Settings View", classes="view-title"),
            Static("\nConfiguration options will appear here."),
            Static("\nPress [d] for Dashboard or [q] to quit"),
        )
