"""Devices Monitor View"""

from textual.widgets import Static, Button, DataTable, Label
from textual.containers import Container, Vertical, Horizontal
from datetime import datetime


class DevicesView(Vertical):
    """Device monitoring view"""
    
    CSS = """
    DevicesView {
        padding: 1;
    }
    
    #devices-header {
        height: auto;
        padding: 1;
    }
    
    #devices-table {
        height: 1fr;
        margin: 1;
    }
    
    #device-details {
        height: 6;
        border: solid blue;
        padding: 1;
        margin: 1;
    }
    """
    
    def __init__(self, server=None, **kwargs):
        super().__init__(**kwargs)
        self.server = server
        self.selected_device = None
    
    def compose(self):
        """Create view layout"""
        yield Container(
            Label("📱 Device Monitor", classes="view-title"),
            Container(
                Static("All Devices: 0", id="all-devices-label"),
                Static("Federated Devices: 0", id="federated-devices-label"),
                id="devices-header"
            ),
            Label("All Devices", classes="table-title"),
            DataTable(id="all-devices-table"),
            Label("Current Federated Round", classes="table-title"),
            DataTable(id="federated-devices-table"),
        )
        
        # Device table
        table = DataTable(id="devices-table")
        table.add_columns("Device ID", "Status", "Last Seen", "Round", "Progress")
        yield table
        
        # Device details panel
        yield Container(
            Static("Select a device to view details", id="device-details-content"),
            id="device-details"
        )
    
    def on_mount(self):
        """Setup when view is mounted"""
        # Setup all devices table
        all_table = self.query_one("#all-devices-table", DataTable)
        all_table.add_columns("Device ID", "Status", "Last Seen")
        all_table.cursor_type = "row"
        
        # Setup federated devices table
        fed_table = self.query_one("#federated-devices-table", DataTable)
        fed_table.add_columns("Device ID", "Round", "Progress", "Status")
        fed_table.cursor_type = "row"
        
        self.set_interval(2.0, self.refresh_devices)
    
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
        
        # Update federated devices table
        fed_table = self.query_one("#federated-devices-table", DataTable)
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
        
        # Update labels
        all_label = self.query_one("#all-devices-label", Static)
        all_label.update(f"All Devices: {len(connected_clients)}")
        
        fed_label = self.query_one("#federated-devices-label", Static)
        fed_label.update(f"Federated Devices: {len(federated_clients)}")
