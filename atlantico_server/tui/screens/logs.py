"""Logs Viewer Screen"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, RichLog, Header
from textual.containers import Container, Vertical, ScrollableContainer
from rich.highlighter import Highlighter, ReprHighlighter
from rich.text import Text
import re, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from atlantico_server.tui.app import CustomFooter


class LogHighlighter(Highlighter):
    """Custom highlighter for log entries - combines ReprHighlighter with custom log level highlighting"""
    
    def __init__(self):
        super().__init__()
        self.base_highlighter = ReprHighlighter()
    
    # Define regex patterns for highlighting
    highlights = [
        r"(?P<timestamp>\[\d{2}:\d{2}:\d{2}(?:\.\d{3})?\])",  # Matches [HH:MM:SS] or [HH:MM:SS.mmm]
        r"(?P<debug>\(DEBUG\))",
        r"(?P<info>\(INFO\))",
        r"(?P<warning>\(WARNING\))",
        r"(?P<error>\(ERROR\))",
        r"(?P<critical>\(CRITICAL\))",
    ]
    
    # Style mapping for log groups
    STYLES = {
        "timestamp": "bright_black",
        "debug": "dim cyan",
        "info": "green",
        "warning": "yellow",
        "error": "red",
        "critical": "bold red",
    }
    
    def highlight(self, text: Text) -> None:
        """Highlight log levels and timestamps using regex patterns, plus ReprHighlighter"""
        # First apply ReprHighlighter for strings, numbers, booleans, etc.
        self.base_highlighter.highlight(text)
        
        # Then apply our custom log highlighting on top (overrides ReprHighlighter styles)
        for pattern in self.highlights:
            for match in re.finditer(pattern, text.plain):
                if match.lastgroup and match.lastgroup in self.STYLES:
                    text.stylize(self.STYLES[match.lastgroup], match.start(), match.end())


class LogsScreen(Screen):
    """Logs viewer screen"""
    
    def __init__(self, server=None, log_file="run/logs/server.log"):
        super().__init__()
        self.server = server
        self.log_file = log_file
        self.last_position = 0
        self.line_count = 0
        self._refresh_timer = None
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        log_container = Container(
            Static(f"Tailing {self.log_file} (auto-refreshes every 0.5s)", id="log-count"),
            RichLog(id="log-display", highlight=True, markup=True),
            classes="panel"
        )
        log_container.border_title = "Server Logs"
        yield log_container
        
        footer = CustomFooter(id="custom-footer")
        footer.current_view = "logs"
        yield footer
    
    def on_mount(self):
        """Setup log refresh"""
        log_widget = self.query_one("#log-display", RichLog)
        log_widget.highlighter = LogHighlighter()
        log_widget.auto_scroll = False
 
    def on_show(self):
        """Start refreshing when screen becomes visible"""
        self.refresh_logs()
        self._refresh_timer = self.set_interval(0.5, self.refresh_logs)

    def on_hide(self):
        """Stop refreshing when screen is hidden"""
        if self._refresh_timer:
            self._refresh_timer.stop()
    
    def refresh_logs(self, scroll_end: bool = True):
        """Tail the log file and display new lines"""
        log_widget = self.query_one("#log-display", RichLog)
        count_widget = self.query_one("#log-count", Static)
        
        if not os.path.exists(self.log_file):
            if self.line_count == 0:
                log_widget.write("Waiting for log file to be created...")
            return
        
        try:
            with open(self.log_file, 'r') as f:
                f.seek(self.last_position)
                new_lines = f.readlines()
                
                if new_lines:
                    for line in new_lines:
                        # Strip milliseconds from display: [HH:MM:SS.mmm] -> [HH:MM:SS]
                        display_line = re.sub(r'\[(\d{2}:\d{2}:\d{2})\.\d{3}\]', r'[\1]', line.rstrip())
                        log_widget.write(display_line, scroll_end=scroll_end)
                        self.line_count += 1
                    
                    self.last_position = f.tell()
                    count_widget.update(f"Tailing {self.log_file} - Total lines: {self.line_count}")
        except Exception as e:
            if self.line_count == 0:
                log_widget.write(f"Error reading log file: {e}")
