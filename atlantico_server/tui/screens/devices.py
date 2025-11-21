"""Devices Monitor Screen"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Button, DataTable, Header
from textual.containers import Container, Vertical, Horizontal
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from atlantico_server.tui.app import CustomFooter


class DevicesScreen(Screen):
    """Devices screen"""
    
    AUTO_FOCUS = False
    
    BINDINGS = [
        ("<", "cycle_sort_left", "Sort prev column"),
        (">", "cycle_sort_right", "Sort next column"),
        ("space", "toggle_device_info", "Toggle device info"),
    ]
    
    def __init__(self, server=None):
        super().__init__()
        self.server = server
        self.selected_device = None
        self._refresh_timer = None
        self._all_table_sort = "device_id"
        self._fed_table_sort = "device_id"
        self._all_table_columns = ["device_id", "status", "last_seen"]
        self._fed_table_columns = ["device_id", "round", "progress", "status"]
        self._info_panel_visible = True
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        with Vertical():
            # Side-by-side layout using Horizontal container
            with Horizontal(id="tables-container"):
                # All devices table with overlaid count
                all_devices_container = Container(
                    DataTable(id="all-devices-table"),
                    Static("Total: 0", id="all-devices-count", classes="table-count"),
                    classes="panel"
                )
                all_devices_container.border_title = "All Devices"
                yield all_devices_container
                
                # Federated devices table with overlaid count
                federated_container = Container(
                    DataTable(id="federated-devices-table"),
                    Static("Total: 0", id="federated-devices-count", classes="table-count"),
                    classes="panel"
                )
                federated_container.border_title = "Current Federated Round"
                yield federated_container
            
            # Device info panel (initially hidden)
            with Container(id="device-info-panel", classes="panel"):
                yield Static("No device selected", id="device-info-content")
        
        footer = CustomFooter(id="custom-footer")
        footer.current_view = "devices"
        yield footer
    
    def on_mount(self):
        """Setup when mounted"""
        all_table = self.query_one("#all-devices-table", DataTable)
        all_table.add_column("Device ID", key="device_id")
        all_table.add_column("Status", key="status")
        all_table.add_column("Last Seen", key="last_seen")
        all_table.cursor_type = "row"
        
        fed_table = self.query_one("#federated-devices-table", DataTable)
        fed_table.add_column("Device ID", key="device_id")
        fed_table.add_column("Round", key="round")
        fed_table.add_column("Status", key="status")
        fed_table.cursor_type = "row"
            
        # Hide info panel initially
        info_panel = self.query_one("#device-info-panel")
        info_panel.display = self._info_panel_visible
    
    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Handle column header clicks to sort the table"""
        table = event.data_table
        
        # Track sort state for each table
        if table.id == "all-devices-table":
            if self._all_table_sort == event.column_key:
                self._all_table_sort = None
            else:
                self._all_table_sort = event.column_key
        elif table.id == "federated-devices-table":
            if self._fed_table_sort == event.column_key:
                self._fed_table_sort = None
            else:
                self._fed_table_sort = event.column_key
        
        table.sort(event.column_key)
        self._update_table_titles()
    
    def action_cycle_sort_left(self) -> None:
        """Cycle to previous sort column"""
        focused = self.focused
        if not isinstance(focused, DataTable):
            return
        
        if focused.id == "all-devices-table":
            current_idx = self._all_table_columns.index(self._all_table_sort) if self._all_table_sort else 0
            new_idx = (current_idx - 1) % len(self._all_table_columns)
            self._all_table_sort = self._all_table_columns[new_idx]
            focused.sort(self._all_table_sort)
        elif focused.id == "federated-devices-table":
            current_idx = self._fed_table_columns.index(self._fed_table_sort) if self._fed_table_sort else 0
            new_idx = (current_idx - 1) % len(self._fed_table_columns)
            self._fed_table_sort = self._fed_table_columns[new_idx]
            focused.sort(self._fed_table_sort)
        
        self._update_table_titles()
    
    def action_cycle_sort_right(self) -> None:
        """Cycle to next sort column"""
        focused = self.focused
        if not isinstance(focused, DataTable):
            return
        
        if focused.id == "all-devices-table":
            current_idx = self._all_table_columns.index(self._all_table_sort) if self._all_table_sort else -1
            new_idx = (current_idx + 1) % len(self._all_table_columns)
            self._all_table_sort = self._all_table_columns[new_idx]
            focused.sort(self._all_table_sort)
        elif focused.id == "federated-devices-table":
            current_idx = self._fed_table_columns.index(self._fed_table_sort) if self._fed_table_sort else -1
            new_idx = (current_idx + 1) % len(self._fed_table_columns)
            self._fed_table_sort = self._fed_table_columns[new_idx]
            focused.sort(self._fed_table_sort)
        
        self._update_table_titles()
    
    def _update_table_titles(self) -> None:
        """Update table border titles with current sort info"""
        all_container = self.query_one("#all-devices-table").parent
        fed_container = self.query_one("#federated-devices-table").parent
        
        # Map keys to readable names
        name_map = {
            "device_id": "Device ID",
            "status": "Status",
            "last_seen": "Last Seen",
            "round": "Round",
            "progress": "Progress"
        }
        
        all_title = "All Devices"
        if self._all_table_sort:
            all_title += f" [dim](sort by [<] {name_map.get(self._all_table_sort, self._all_table_sort)} [>])[/dim]"
        all_container.border_title = all_title
        
        fed_title = "Current Federated Round"
        if self._fed_table_sort:
            fed_title += f" [dim](sort by [<] {name_map.get(self._fed_table_sort, self._fed_table_sort)} [>])[/dim]"
        fed_container.border_title = fed_title
    
    def action_toggle_device_info(self) -> None:
        """Toggle device info panel visibility"""
        info_panel = self.query_one("#device-info-panel")
        self._info_panel_visible = not self._info_panel_visible
        info_panel.display = self._info_panel_visible
        
        if self._info_panel_visible:
            self._update_device_info()
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in tables"""
        self.selected_device = event.row_key.value if hasattr(event.row_key, 'value') else str(event.row_key)
        if self._info_panel_visible:
            self._update_device_info()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update info panel on row navigation (highlight)"""
        self.selected_device = event.row_key.value if hasattr(event.row_key, 'value') else str(event.row_key)
        if self._info_panel_visible:
            self._update_device_info()
    
    def _update_device_info(self) -> None:
        """Update device info panel content"""
        info_content = self.query_one("#device-info-content", Static)
        info_panel = self.query_one("#device-info-panel")
        
        if not self.selected_device or not self.server:
            info_content.update("No device selected [dim]\\[space][/dim]")
            info_panel.border_title = "Selected Device Info [dim]\\[space][/dim]"
            return
        
        import time
        connected_clients = getattr(self.server.state, 'connected_clients', {})
        federated_clients = getattr(self.server.state, 'federated_clients', {})
        
        device_info = connected_clients.get(self.selected_device, {})
        fed_info = federated_clients.get(self.selected_device, {})
        
        if not device_info:
            info_content.update(f"Device {self.selected_device} not found [dim]\\[space][/dim]")
            info_panel.border_title = f"Selected Device Info [dim]\\[space][/dim]"
            return
        
        # Calculate status
        last_seen_time = device_info.get('last_seen', 0)
        seconds_ago = time.time() - last_seen_time
        is_alive = seconds_ago < 35
        
        if is_alive:
            status = "[green]● Alive[/green]"
        else:
            status = "[red]○ Dead[/red]"
        last_seen = f"{int(seconds_ago)}s ago"
        
        # Build info display
        lines = [
            f"[bold]Device ID:[/bold] {self.selected_device}",
            f"[bold]Status:[/bold] {status}",
            f"[bold]Last Seen:[/bold] {last_seen}",
        ]
        # Federated info
        if fed_info:
            round_num = fed_info.get('round', '-')
            fed_status = "[green]● Active[/green]" if is_alive else "[dim red]○ Offline[/dim red]"
            lines.extend([
                "",
                f"[bold]Federated Round:[/bold] {round_num}",
                f"[bold]Federated Status:[/bold] {fed_status}",
            ])
        
        # Placeholder for future data
        lines.extend([
            "",
            f"[bold]IP:[/bold] [dim]Not available[/dim]",
            f"[bold]MAC:[/bold] [dim]Not available[/dim]",
            f"[bold]Version:[/bold] [dim]Not available[/dim]",
        ])
        
        info_content.update("\n".join(lines))
        info_panel.border_title = f"Selected Device Info - {self.selected_device} [dim]\\[space][/dim]" 
    
    def on_show(self):
        """Start refreshing when screen becomes visible"""
        self.refresh_devices()
        self._refresh_timer = self.set_interval(1.0, self.refresh_devices)
    
    def on_hide(self):
        """Stop refreshing when screen is hidden"""
        if self._refresh_timer:
            self._refresh_timer.stop()
    
    def refresh_devices(self):
        """Refresh device lists from server state"""
        if not self.server:
            return
        
        import time
        
        # Get data from server state (now dicts, not lists)
        connected_clients = getattr(self.server.state, 'connected_clients', {})
        federated_clients = getattr(self.server.state, 'federated_clients', {})
        
        # Update all devices table
        all_table = self.query_one("#all-devices-table", DataTable)
        saved_cursor = all_table.cursor_row
        all_table.clear()
        
        for device_id, device_info in connected_clients.items():
            last_seen_time = device_info.get('last_seen', 0)
            seconds_ago = time.time() - last_seen_time
            is_alive = seconds_ago < 35  # Alive if seen in last 35 seconds
            
            # Color-coded status with Rich markup
            if is_alive:
                status = "[green]● Alive[/green]"
                status_sort = 0  # Alive sorts first
                last_seen = "Just now"
            else:
                status = "[red]○ Dead[/red]"
                status_sort = 1  # Dead sorts second
                if seconds_ago < 60:
                    last_seen = f"{int(seconds_ago)}s ago"
                elif seconds_ago < 3600:
                    last_seen = f"{int(seconds_ago/60)}m ago"
                else:
                    last_seen = f"{int(seconds_ago/3600)}h ago"
            
            all_table.add_row(device_id, status, last_seen, key=device_id)
        
        # Reapply sort if one was active
        if self._all_table_sort:
            all_table.sort(self._all_table_sort)
        
        if saved_cursor is not None and saved_cursor < all_table.row_count:
            all_table.move_cursor(row=saved_cursor)
        
        # Update federated devices table
        fed_table = self.query_one("#federated-devices-table", DataTable)
        saved_fed_cursor = fed_table.cursor_row
        fed_table.clear()
        
        for device_id, device_info in federated_clients.items():
            round_num = device_info.get('round', '-')
            progress = device_info.get('progress', '-')
            
            # Check if device is alive based on connected_clients timestamp
            if device_id in connected_clients:
                seconds_ago = time.time() - connected_clients[device_id].get('last_seen', 0)
                is_alive = seconds_ago < 35
            else:
                is_alive = False
            
            # Color-coded status with Rich markup
            status = "[green]● Active[/green]" if is_alive else "[dim red]○ Offline[/dim red]"
            status_sort = 0 if is_alive else 1
            
            fed_table.add_row(device_id, str(round_num), str(progress), status, key=device_id)
        
        # Reapply sort if one was active
        if self._fed_table_sort:
            fed_table.sort(self._fed_table_sort)
        
        if saved_fed_cursor is not None and saved_fed_cursor < fed_table.row_count:
            fed_table.move_cursor(row=saved_fed_cursor)
        
        # Update overlaid count labels
        all_count = self.query_one("#all-devices-count", Static)
        all_count.update(f"Total: {len(connected_clients)}")
        
        fed_count = self.query_one("#federated-devices-count", Static)
        fed_count.update(f"Total: {len(federated_clients)}")
        
        # Update titles with sort info
        self._update_table_titles()



