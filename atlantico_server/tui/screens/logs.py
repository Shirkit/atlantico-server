"""Logs Viewer View"""

from textual.widgets import Static, Label, RichLog
from textual.containers import Container, Vertical, ScrollableContainer
import os


class LogsView(Vertical):
    """Logs viewer view - tails the server log file"""
    
    CSS = """
    LogsView {
        layout: vertical;
        padding: 1;
    }
    
    #log-display {
        height: 1fr;
        border: solid green;
        padding: 1;
        overflow-y: auto;
    }
    """
    
    def __init__(self, server=None, log_file="run/logs/server.log", **kwargs):
        super().__init__(**kwargs)
        self.server = server
        self.log_file = log_file
        self.last_position = 0
        self.line_count = 0
    
    def compose(self):
        """Create view layout"""
        yield Label("📋 Server Logs", classes="view-title")
        yield Static(f"Tailing {self.log_file} (auto-refreshes every 0.5s)", id="log-count")
        yield RichLog(id="log-display", highlight=True, markup=True)
    
    def on_mount(self):
        """Setup log refresh"""
        self.set_interval(0.5, self.refresh_logs)
        self.refresh_logs()
    
    def refresh_logs(self):
        """Tail the log file and display new lines"""
        log_widget = self.query_one("#log-display", RichLog)
        count_widget = self.query_one("#log-count", Static)
        
        if not os.path.exists(self.log_file):
            if self.line_count == 0:
                log_widget.write("Waiting for log file to be created...")
            return
        
        try:
            with open(self.log_file, 'r') as f:
                # Seek to last position
                f.seek(self.last_position)
                
                # Read new lines
                new_lines = f.readlines()
                
                if new_lines:
                    for line in new_lines:
                        log_widget.write(line.rstrip())
                        self.line_count += 1
                    
                    # Update position
                    self.last_position = f.tell()
                    
                    # Update count
                    count_widget.update(f"Tailing {self.log_file} - Total lines: {self.line_count}")
        except Exception as e:
            if self.line_count == 0:
                log_widget.write(f"Error reading log file: {e}")
