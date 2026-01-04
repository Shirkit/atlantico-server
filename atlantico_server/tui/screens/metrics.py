from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, DataTable, Button, Header, Select, TabbedContent, TabPane, DirectoryTree, Label, Input
from textual.screen import Screen
from textual.reactive import reactive
from atlantico_server.parser import _find_json_files, _load_json_data
from atlantico_server.tui.app import CustomFooter
from textual_plotext import PlotextPlot
import os
from typing import Iterable
from pathlib import Path
from collections import defaultdict

class FilteredDirectoryTree(DirectoryTree):
    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [path for path in paths if path.is_dir() or path.name.endswith("json")]

class MetricsScreen(Screen):
    """Screen for displaying training metrics"""

    # Reactive state for data and selection
    current_metric = reactive("accuracy")
    available_metrics = reactive([])

    BINDINGS = [
        ("space", "toggle_folder_pick_panel", "Toggle folder picker panel"),
    ]

    def __init__(self, server=None):
        super().__init__()
        self.server = server
        self.json_data = []
        self._folder_panel_visible = False
        self._picked_folder = ""

    def compose(self) -> ComposeResult:
        yield Header()
        
        with Container(id="metrics-container"):
            # Controls Area
            with Horizontal(id="metrics-controls"):
                self.test_select = Select([], prompt="Select Test", id="test-select", disabled=True, allow_blank=True)
                self.metric_select = Select([], prompt="Select Metric", id="metric-select", allow_blank=True)
                self.status_label = Static("", id="metrics-status")

                yield Button("Refresh Data", id="refresh-btn", variant="primary")
                yield self.test_select
                yield self.metric_select
                
                yield self.status_label

            # Summary Area
            with Horizontal(id="metrics-summary"):
                self.summary_rounds = Static("Total Rounds: -", id="summary-rounds", classes="summary-box")
                yield self.summary_rounds
                self.summary_accuracy = Static("Best Accuracy: -", id="summary-accuracy", classes="summary-box")
                yield self.summary_accuracy
                self.summary_time = Static("Avg Training Time: -", id="summary-time", classes="summary-box")
                yield self.summary_time
            
            # Content Area (Tabs for Table and Plot)
            with TabbedContent(initial="plot-tab"):
                with TabPane("Visualizations", id="plot-tab"):
                    self.plot = PlotextPlot(id="metrics-plot")
                    yield self.plot
                
                with TabPane("Data Table", id="table-tab"):
                    # Create and configure table here to ensure it exists
                    self.table = DataTable(id="metrics-table")
                    self.table.add_columns("Round", "Client", "Accuracy", "Loss (MSE)", "F1 Score", "Training Time (s)")
                    self.table.cursor_type = "row"
                    self.table.zebra_stripes = True
                    yield self.table

        with Container(id="folder-pick-panel", classes="panel"):
            yield Horizontal(
                Label("Batch:", classes="config-label"),
                Input(value=self._picked_folder, placeholder="Pick a folder", id="folder-pick-input", classes="config-input"),
            )
            d = DirectoryTree(Path("."), id="folder-tree")
            yield d

        footer = CustomFooter(id="custom-footer")
        footer.current_view = "metrics"
        yield footer
            
    def on_mount(self) -> None:
        """Initialize the screen"""
        # Try to load data if available
        self.load_data()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-btn":
            self.load_data()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "metric-select" and event.value:
            self.current_metric = event.value
            self.update_plot()
        elif event.select.id == "test-select":
            self.load_data()

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        """Handle directory selection from directory tree"""
        if event.path.name.find("batch") != -1:
            batch_input = self.query_one("#folder-pick-input", Input)
            batch_input.value = str(event.path)
            self.load_data()

    def action_toggle_folder_pick_panel(self) -> None:
        """Toggle folder picker panel visibility"""
        panel = self.query_one("#folder-pick-panel", Container)
        metrics = self.query_one("#metrics-container", Container)
        self._folder_panel_visible = not getattr(self, "_folder_panel_visible", False)
        panel.display = self._folder_panel_visible
        metrics.display = not self._folder_panel_visible
        
    def load_data(self) -> None:
        """Load metrics data from the server's parse folder"""
        if not self.server:
            self.app.notify("Server instance not available", severity="error")
            return

        # Determine where to look for data
        target_path = None
        batch_path = self.server.state.batch_base_path
        current_federated = self.server.state.federated_path

        input = self.query_one("#folder-pick-input", Input)
        if input.value:
            batch_path = input.value
            # TODO: we may not have a batch path, instead a path to a single test folder

        # Check if we are in batch mode
        if batch_path and os.path.exists(batch_path):
            # Find test folders (subdirectories in batch folder)
            try:
                subdirs = [d for d in os.listdir(batch_path) 
                          if os.path.isdir(os.path.join(batch_path, d)) and not d.startswith('.')]
                subdirs.sort()

                # Update test selector options
                with self.test_select.prevent(Select.Changed):
                    current_val = self.test_select.value
                    options = [(d, d) for d in subdirs]
                    
                    self.test_select.set_options(options)
                    self.test_select.disabled = False
                    
                    # Determine which test to load
                    if current_val and current_val in subdirs:
                        # User selected a specific test, keep it
                        if self.test_select.value != current_val:
                            self.test_select.value = current_val
                        target_path = os.path.join(batch_path, current_val)
                    elif current_federated and current_federated.startswith(batch_path):
                        # Auto-select current running test
                        rel_path = os.path.relpath(current_federated, batch_path)
                        # Only set if it's a direct child (valid test folder)
                        if rel_path in subdirs:
                            self.test_select.value = rel_path
                            target_path = current_federated
                        else:
                            target_path = current_federated
                    elif subdirs:
                        # Default to the most recent test
                        latest_test = subdirs[-1]
                        self.test_select.value = latest_test
                        target_path = os.path.join(batch_path, latest_test)
                    else:
                        # No subdirs found yet, fallback to batch root
                        target_path = batch_path
            except Exception as e:
                self.status_label.update(f"Error listing batch tests: {str(e)}")
                return
        else:
            # Single run mode
            with self.test_select.prevent(Select.Changed):
                self.test_select.clear()
                self.test_select.set_options([])
                self.test_select.disabled = True
            
            if current_federated:
                target_path = current_federated
            elif os.path.exists("parse/"):
                target_path = "parse/"

        if not target_path or not os.path.exists(target_path):
            self.status_label.update("No data folder found")
            return

        self.status_label.update(f"Loading from {os.path.basename(target_path)}...")
        
        try:
            found_files = _find_json_files(target_path)
            if not found_files:
                self.status_label.update("No JSON files")
                # Clear data if no files found
                self.json_data = []
                self._update_table()
                self._update_summary()
                if hasattr(self, 'plot'):
                    self.plot.plt.clear_figure()
                    self.plot.refresh()
                return

            # self.app.notify(str(len(found_files)) + " JSON files found", severity="info")

            self.json_data = _load_json_data(found_files)
            # s = ""
            # for f in found_files:
            #     s = s + f + "\n"
            # self.app.notify(f"{s}", severity="info")
            # self.app.notify(f"Loaded {len(self.json_data)} records", severity="info")
            if not self.json_data:
                self.status_label.update("No valid data")
                return

            # Update UI components
            self._update_metrics_list()
            self._update_table()
            self._update_summary()
            self.update_plot()
            
            self.status_label.update(f"Loaded {len(self.json_data)} records")
            
        except Exception as e:
            self.status_label.update(f"Error: {str(e)}")

    def _update_metrics_list(self):
        """Update the list of available metrics based on loaded data"""
        if not self.json_data:
            return
            
        # Find all unique metric keys
        metrics = set()
        for item in self.json_data:
            if "metrics" in item:
                metrics.update(item["metrics"].keys())
        
        # Filter out non-numeric metrics if any, or keep all
        # Common metrics: accuracy, meanSqrdError, f1Score, precision, recall
        sorted_metrics = sorted(list(metrics))

        # Update Select widget
        if hasattr(self, 'metric_select'):
            options = [(m.replace("meanSqrdError", "Loss (MSE)").title(), m) for m in sorted_metrics]
            options = [opt for opt in options if opt[1] not in {"trueNegatives", "truePositives", "falseNegatives", "falsePositives", "numberOfClasses"}]
            self.metric_select.set_options(options)

            # Set default if current not in list
            if self.current_metric not in metrics and metrics:
                # Prefer accuracy or meanSqrdError
                if "accuracy" in metrics:
                    self.metric_select.value = "accuracy"
                elif "meanSqrdError" in metrics:
                    self.metric_select.value = "meanSqrdError"
                else:
                    self.metric_select.value = sorted_metrics[0]

    def _update_table(self):
        """Update the data table with loaded metrics"""
        if not hasattr(self, 'table'):
            return
            
        self.table.clear()
        
        # Sort by round, then client
        sorted_data = sorted(self.json_data, key=lambda x: (x.get("round", 0), x.get("client", "")))
        
        for item in sorted_data:
            round_num = item.get("round", 0)
            client = item.get("client", "Unknown")
            metrics = item.get("metrics", {})
            timings = item.get("timings", {})
            
            accuracy = f"{float(metrics.get('accuracy', 0)):.4f}"
            loss = f"{float(metrics.get('meanSqrdError', 0)):.4f}"
            f1 = f"{float(metrics.get('f1Score', 0)):.4f}"
            
            training_time = timings.get("training", 0)
            training_time_s = f"{training_time / 1000:.2f}" if training_time else "-"
            
            self.table.add_row(
                str(round_num),
                str(client),
                accuracy,
                loss,
                f1,
                training_time_s
            )

    def _update_summary(self):
        """Update summary statistics"""
        if not self.json_data:
            return
            
        rounds = set(item.get("round", 0) for item in self.json_data)
        accuracies = [float(item.get("metrics", {}).get("accuracy", 0)) for item in self.json_data if "accuracy" in item.get("metrics", {})]
        training_times = [item.get("timings", {}).get("training", 0) / 1000 for item in self.json_data if "training" in item.get("timings", {})]
        
        total_rounds = len(rounds)
        best_accuracy = max(accuracies) if accuracies else 0
        avg_time = sum(training_times) / len(training_times) if training_times else 0
        
        self.summary_rounds.update(f"Total Rounds: {total_rounds}")
        self.summary_accuracy.update(f"Best Accuracy: {best_accuracy:.4f}")
        self.summary_time.update(f"Avg Training Time: {avg_time:.2f}s")

    def update_plot(self) -> None:
        """Render the plot for the current metric"""
        if not self.json_data or not hasattr(self, 'plot'):
            return
            
        plt = self.plot.plt
        plt.clear_figure()
        
        metric_name = self.current_metric
        
        # Organize data by client
        client_data = defaultdict(list)
        rounds_set = set()
        
        for item in self.json_data:
            if "metrics" in item and metric_name in item["metrics"]:
                try:
                    val = float(item["metrics"][metric_name])
                    r = item.get("round", 0)
                    client = item.get("client", "Unknown")
                    client_data[client].append((r, val))
                    rounds_set.add(r)
                except (ValueError, TypeError):
                    continue
        
        if not client_data:
            return

        # Plot individual clients
        for client, points in client_data.items():
            points.sort(key=lambda x: x[0])
            x = [p[0] for p in points]
            y = [p[1] for p in points]
            plt.plot(x, y, label=client)

        # Calculate and plot average
        sorted_rounds = sorted(list(rounds_set))
        avg_values = []
        for r in sorted_rounds:
            vals = []
            for points in client_data.values():
                for pr, pv in points:
                    if pr == r:
                        vals.append(pv)
            if vals:
                avg_values.append(sum(vals) / len(vals))
            else:
                avg_values.append(0)
        
        plt.plot(sorted_rounds, avg_values, label="Average", color="white")

        # Styling
        plt.title(f"Evolution of {metric_name} over Rounds")
        plt.xlabel("Round")
        plt.ylabel(metric_name)
        plt.grid(False, False)
        
        # Refresh the widget
        self.plot.refresh()
