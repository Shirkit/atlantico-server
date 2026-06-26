"""Settings Screen"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Header, Switch, Button, Checkbox, Select, Label, Input
from textual.containers import Container, Vertical, Horizontal
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from atlantico_server.tui.app import CustomFooter
from atlantico_server import strategies

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
            Checkbox("Show Date in Logs", value=self.app.config["display"]["show_date"], id="switch-show-date"),
            Button("Clear Logs", id="btn-clear-logs", variant="error"),
            classes="panel"
        )
        container.border_title = "Logs Configuration"
        yield container

        mqtt_container = Vertical(
            Label("Client Topic Prefix:", classes="config-label"),
            Select.from_values(["esp32", "rasp", "aggregator"], value=self.app.config["mqtt"]["topic_prefix"], id="select-topic-prefix", allow_blank=False),
            classes="panel"
        )
        mqtt_container.border_title = "MQTT Configuration"
        yield mqtt_container

        strategies_list = strategies.GetListOfStrategies()

        hierarchical_container = Vertical(
            Checkbox("Enable Hierarchical Mode", value=self.app.config["hierarchical"]["enabled"], id="switch-hierarchical"),
            Label("Parent Topic Prefix:", classes="config-label", id="label-parent-prefix"),
            Select([("aggregator", "aggregator")], value=self.app.config["hierarchical"]["parent_prefix"], id="select-parent-prefix", allow_blank=False),
            Label("Sliding Window Size (Bounded Asynchronous):", classes="config-label", id="label-sliding-window"),
            Input(str(self.app.config["hierarchical"].get("sliding_window", "") or ""), id="input-sliding-window", placeholder="Default: 10"),
            classes="panel"
        )
        hierarchical_container.border_title = "Hierarchical Federation"
        yield hierarchical_container

        aggregration_container = Vertical(
            Label("Process Type:", classes="config-label"),
            Select(strategies_list["process_type"], value=self.app.config["hierarchical"]["process_type"], id="select-process-type", allow_blank=False),
            Label("Merge Strategy:", classes="config-label"),
            Select(strategies_list["merge_strategy"], value=self.app.config["hierarchical"]["merge_strategy"], id="select-merge-strategy", allow_blank=False),
            Label("Aggregation Algorithm:", classes="config-label"),
            Select(strategies_list["aggregation_algorithm"], value=self.app.config["hierarchical"]["aggregation_algorithm"], id="select-aggregation-algorithm", allow_blank=False),
            Label("Maximum Waiting Time for Clients per Round (seconds):", classes="config-label"),
            Input(str(self.app.config["max_wait_time"]), id="input-max-wait-time", placeholder="Leave empty for disabled"),
            classes="panel"
        )
        aggregration_container.border_title = "Aggregration Options"
        yield aggregration_container

        footer = CustomFooter(id="custom-footer")
        footer.current_view = "settings"
        yield footer
            
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "btn-clear-logs":
            self.clear_logs()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes"""
        if event.input.id == "input-max-wait-time":
            value = event.value.strip()
            try:
                int_value = int(value)
                if int_value < 0:
                    raise ValueError
                self.app.config["max_wait_time"] = value
                self.app._save_config()
            except ValueError:
                self.app.notify("Please enter a valid non-negative integer for Maximum Waiting Time.", severity="error")
                return
            self.app._save_config()
        elif event.input.id == "input-sliding-window":
            value = event.value.strip()
            if value == "":
                self.app.config["hierarchical"]["sliding_window"] = ""
                self.app._save_config()
                return
            try:
                int_value = int(value)
                if int_value < 1:
                    raise ValueError
                self.app.config["hierarchical"]["sliding_window"] = int_value
                self.app._save_config()
            except ValueError:
                self.app.notify("Please enter a valid positive integer for Sliding Window Size.", severity="error")
                return

    def on_mount(self) -> None:
        """Call update_visibility when settings screen is mounted"""
        self.update_visibility()

    def update_visibility(self) -> None:
        """Dynamically show/hide fields based on configuration values"""
        try:
            hierarchical_enabled = self.app.config["hierarchical"]["enabled"]
            
            # Show/hide Parent Topic Prefix widgets
            self.query_one("#label-parent-prefix").display = hierarchical_enabled
            self.query_one("#select-parent-prefix").display = hierarchical_enabled
            
            # Show/hide Sliding Window widgets based on:
            # - Client topic prefix == "aggregator"
            # - Sync Strategy == "BoundedAsynchronousStrategy"
            client_prefix = self.app.config["mqtt"]["topic_prefix"]
            process_type = self.app.config["hierarchical"]["process_type"]
            
            show_sliding = (client_prefix == "aggregator" and process_type == "BoundedAsynchronousStrategy")
            
            self.query_one("#label-sliding-window").display = show_sliding
            self.query_one("#input-sliding-window").display = show_sliding
        except Exception:
            pass

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes"""
        if event.checkbox.id == "switch-show-date":
            self.app.config["display"]["show_date"] = event.value
            self.app._save_config()
        elif event.checkbox.id == "switch-hierarchical":
            self.app.config["hierarchical"]["enabled"] = event.value
            self.app._save_config()
            self.update_visibility()
            self.app.notify("A server restart is required to apply hierarchical settings.")
            
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes"""
        if event.select.id == "select-topic-prefix" and event.value != self.app.config["mqtt"]["topic_prefix"]:
            self.app.config["mqtt"]["topic_prefix"] = event.value
            self.app._save_config()
            self.update_visibility()
            self.app.notify(f"A server restart is required to apply the new topic prefix.")
        elif event.select.id == "select-parent-prefix" and event.value != self.app.config["hierarchical"]["parent_prefix"]:
            self.app.config["hierarchical"]["parent_prefix"] = event.value
            self.app._save_config()
            self.app.notify("A server restart is required to apply hierarchical settings.")
        elif event.select.id == "select-process-type" and event.value != self.app.config["hierarchical"]["process_type"]:
            self.app.config["hierarchical"]["process_type"] = event.value
            self.app._save_config()
            self.update_visibility()
            self.app.notify("A server restart is required to apply hierarchical settings.")
        elif event.select.id == "select-merge-strategy" and event.value != self.app.config["hierarchical"]["merge_strategy"]:
            self.app.config["hierarchical"]["merge_strategy"] = event.value
            self.app._save_config()
            self.app.notify("A server restart is required to apply hierarchical settings.")
        elif event.select.id == "select-aggregation-algorithm" and event.value != self.app.config["hierarchical"]["aggregation_algorithm"]:
            self.app.config["hierarchical"]["aggregation_algorithm"] = event.value
            self.app._save_config()
            self.app.notify("A server restart is required to apply hierarchical settings.")

    def clear_logs(self):
        """Clear the log file"""
        log_file = os.environ.get('ATLANTICO_SERVER_LOG', 'run/logs/server.log')
        try:
            with open(log_file, "w") as f:
                f.write("")
        except Exception:
            pass
