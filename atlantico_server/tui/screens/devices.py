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
    
    def __init__(self, server=None):
        super().__init__()
        self.server = server
        self.selected_device = None
        self._refresh_timer = None
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        all_devices_container = Container(
            Container(
                Static("All Devices: 0", id="all-devices-label"),
                Static("Federated Devices: 0", id="federated-devices-label"),
                id="devices-header"
            ),
            DataTable(id="all-devices-table"),
            classes="panel"
        )
        all_devices_container.border_title = "All Devices"
        yield all_devices_container
        
        federated_container = Container(
            DataTable(id="federated-devices-table"),
            classes="panel"
        )
        federated_container.border_title = "Current Federated Round"
        yield federated_container
        
        footer = CustomFooter(id="custom-footer")
        footer.current_view = "devices"
        yield footer
    
    def on_mount(self):
        """Setup when mounted"""
        all_table = self.query_one("#all-devices-table", DataTable)
        all_table.add_columns("Device ID", "Status", "Last Seen")
        all_table.cursor_type = "row"
        
        fed_table = self.query_one("#federated-devices-table", DataTable)
        fed_table.add_columns("Device ID", "Round", "Progress", "Status")
        fed_table.cursor_type = "row"
    
    def on_show(self):
        """Start refreshing when screen becomes visible"""
        self.refresh_devices()
        self._refresh_timer = self.set_interval(2.0, self.refresh_devices)
    
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
            
            status = "● Alive" if is_alive else "○ Dead"
            if is_alive:
                last_seen = "Just now"
            elif seconds_ago < 60:
                last_seen = f"{int(seconds_ago)}s ago"
            elif seconds_ago < 3600:
                last_seen = f"{int(seconds_ago/60)}m ago"
            else:
                last_seen = f"{int(seconds_ago/3600)}h ago"
            
            all_table.add_row(device_id, status, last_seen)
        
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
            
            status = "● Active" if is_alive else "○ Offline"
            fed_table.add_row(device_id, str(round_num), str(progress), status)
        
        if saved_fed_cursor is not None and saved_fed_cursor < fed_table.row_count:
            fed_table.move_cursor(row=saved_fed_cursor)
        
        # Update labels
        all_label = self.query_one("#all-devices-label", Static)
        all_label.update(f"All Devices: {len(connected_clients)}")
        
        fed_label = self.query_one("#federated-devices-label", Static)
        fed_label.update(f"Federated Devices: {len(federated_clients)}")



