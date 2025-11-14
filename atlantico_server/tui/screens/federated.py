"""Federated Learning Control View"""

from textual.widgets import Static
from textual.containers import Container, Vertical


class FederatedView(Vertical):
    """Federated learning control view"""
    
    def __init__(self, server=None, **kwargs):
        super().__init__(**kwargs)
        self.server = server
    
    def compose(self):
        """Create view layout"""
        yield Container(
            Static("🤝 Federated Learning View", classes="view-title"),
            Static("\nFederated learning controls will appear here."),
            Static("\nPress [d] for Dashboard or [q] to quit"),
        )
