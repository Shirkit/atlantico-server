"""Logs Viewer Screen"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, RichLog, Header, Input, Checkbox, Select, Label
from textual.containers import Container, Vertical, ScrollableContainer, Horizontal
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
        r"(?P<timestamp>\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{3})?\])",  # Matches [YYYY-MM-DD HH:MM:SS.mmm]
        r"(?P<timestamp_short>\[\d{2}:\d{2}:\d{2}(?:\.\d{3})?\])",  # Matches [HH:MM:SS.mmm]
        r"(?P<debug>\(DEBUG\))",
        r"(?P<info>\(INFO\))",
        r"(?P<warning>\(WARNING\))",
        r"(?P<error>\(ERROR\))",
        r"(?P<critical>\(CRITICAL\))",
    ]
    
    # Style mapping for log groups
    STYLES = {
        "timestamp": "bright_black",
        "timestamp_short": "bright_black",
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
    
    AUTO_FOCUS = False
    
    def __init__(self, server=None, log_file="run/logs/server.log"):
        super().__init__()
        self.server = server
        self.log_file = log_file
        self.last_position = 0
        self.line_count = 0
        self._refresh_timer = None
        self._last_filter_level = "ALL"
        self._last_search_term = ""
        self._last_show_date = False
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        log_container = Container(
            # Header controls
            Horizontal(
                Static("", id="log-count"),
                Checkbox("Auto Scroll", value=True, id="log-autoscroll"),
                Select(
                    [("Default", "NOT_DEBUG"), ("All Levels", "ALL"), ("Debug", "DEBUG"), ("Info", "INFO"), ("Warning", "WARNING"), ("Error", "ERROR"), ("Critical", "CRITICAL")],
                    value="NOT_DEBUG",
                    id="log-level-filter",
                    allow_blank=False,
                    compact=True
                ),
                Input(placeholder="Search logs...", id="log-search"),
                id="log-header"
            ),
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
        log_widget.auto_scroll = False  # We handle scrolling manually
 
    def on_show(self):
        """Start refreshing when screen becomes visible"""
        self.refresh_logs()
        self._refresh_timer = self.set_interval(0.5, self.refresh_logs)

    def on_hide(self):
        """Stop refreshing when screen is hidden"""
        if self._refresh_timer:
            self._refresh_timer.stop()
            
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input change"""
        if event.input.id == "log-search":
            self.refresh_logs(force_reload=True)
            
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle level filter change"""
        if event.select.id == "log-level-filter":
            self.refresh_logs(force_reload=True)
    
    def refresh_logs(self, force_reload: bool = False):
        """Tail the log file and display new lines"""
        log_widget = self.query_one("#log-display", RichLog)
        count_widget = self.query_one("#log-count", Static)
        search_input = self.query_one("#log-search", Input)
        level_select = self.query_one("#log-level-filter", Select)
        autoscroll_cb = self.query_one("#log-autoscroll", Checkbox)
        
        # Get current settings
        search_term = search_input.value.lower()
        filter_level = level_select.value
        show_date = self.app.config.get("display", {}).get("show_date", False)
        
        # Check if we need to reload everything
        if (force_reload or 
            search_term != self._last_search_term or 
            filter_level != self._last_filter_level or
            show_date != self._last_show_date):
            
            log_widget.clear()
            self.last_position = 0
            self.line_count = 0
            self._last_search_term = search_term
            self._last_filter_level = filter_level
            self._last_show_date = show_date
        
        if not os.path.exists(self.log_file):
            return
            
        try:
            # Check if file was rotated or truncated
            current_size = os.path.getsize(self.log_file)
            if current_size < self.last_position:
                self.last_position = 0
                log_widget.clear()
                self.line_count = 0
            
            with open(self.log_file, "r", encoding="utf-8") as f:
                f.seek(self.last_position)
                new_lines = f.readlines()
                self.last_position = f.tell()
                
                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    # Apply level filter
                    if filter_level != "ALL":
                        if filter_level == "NOT_DEBUG":
                            if "(DEBUG)" in line:
                                continue
                        else:
                            if f"({filter_level})" not in line:
                                continue
                            
                    # Apply search filter
                    if search_term and search_term not in line.lower():
                        continue
                    
                    # Handle date display
                    if not show_date:
                        # Replace [YYYY-MM-DD HH:MM:SS.mmm] with [HH:MM:SS.mmm]
                        line = re.sub(r"^\[\d{4}-\d{2}-\d{2} ", "[", line)
                    
                    log_widget.write(line, scroll_end=autoscroll_cb.value)
                    self.line_count += 1
                    
            count_widget.update(f"Lines: {self.line_count}")
                
        except Exception as e:
            count_widget.update(f"Error reading logs: {str(e)}")
        
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
                    count_widget.update(f"{self.log_file} - {self.line_count} lines")
        except Exception as e:
            if self.line_count == 0:
                log_widget.write(f"Error reading log file: {e}")
