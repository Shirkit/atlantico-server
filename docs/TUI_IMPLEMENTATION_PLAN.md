# Atlantico Server TUI Implementation Plan

## Overview
Transform the atlantico-server from a CLI-based application to a modern Terminal User Interface (TUI) using Textual framework. This will provide real-time monitoring, interactive controls, and better user experience for managing federated learning operations.

## Technology Choice: Textual

**Why Textual?**
- Modern, reactive framework with CSS-like styling
- Built-in async/await support (perfect for MQTT event handling)
- Rich widget library: DataTable, Log, Button, Input, Header, Footer, etc.
- Mouse support in terminal
- Active development and excellent documentation
- Created by Will McGugan (Rich library author)

## Current Architecture Analysis

### Existing Classes
1. **FederatedServerState** - Manages server state
   - `is_federated`, `current_round`, `max_rounds`
   - `connected_clients`, `waiting_for_clients`, `alive_clients`
   - `federated_path`, `debug`

2. **MQTTFederatedServer** - Main server implementation
   - MQTT client management
   - Message handling (models, commands)
   - Federated learning orchestration
   - Batch processing capabilities

### Key Methods to Integrate
- `connect()` - MQTT broker connection
- `listen()` - Start MQTT message loop
- `federate()` - Run federated learning
- `batch()` - Batch federated learning
- `check_alive_devices()` - Monitor device status
- `_handle_*_command()` - Command handlers

## TUI Architecture

### Container Approach (Implemented)

**Architecture Pattern:** Single-screen application with content swapping

The application uses a **container approach** where:
- One main `ServerApp` instance runs throughout the session
- Header and Footer remain visible at all times
- Content area uses `ContentSwitcher` to swap between different views
- All views (Dashboard, Devices, Federated, Logs, Settings) are widgets, not screens
- Navigation is instant - just switches which view is visible

**Benefits:**
- Persistent header/footer navigation
- Faster view switching (no screen push/pop)
- Shared state easier to manage
- More traditional desktop-app feel

### Application Structure
```
atlantico_server/
├── server.py              # Existing server logic (keep as is)
├── tui/
│   ├── __init__.py
│   ├── app.py            # Main Textual app with ContentSwitcher
│   ├── screens/          # Note: "screens" folder contains Views now
│   │   ├── __init__.py
│   │   ├── dashboard.py  # DashboardView - main view
│   │   ├── devices.py    # DevicesView - device monitoring
│   │   ├── federated.py  # FederatedView - training control
│   │   ├── logs.py       # LogsView - logs viewer
│   │   └── settings.py   # SettingsView - configuration
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── device_table.py     # Custom device status table
│   │   ├── metrics_panel.py    # Training metrics display
│   │   ├── status_bar.py       # Server status indicator
│   │   └── log_viewer.py       # Real-time log display
│   └── styles/
│       └── main.css      # Textual CSS styling
└── server_tui.py         # Entry point for TUI mode
```

**Visual Structure:**
```
┌─────────────────────────────────────────────┐
│ Header (Atlantico Server - always visible) │
├─────────────────────────────────────────────┤
│                                             │
│  ContentSwitcher Area:                      │
│  - Shows DashboardView (default)            │
│  - Or DevicesView                           │
│  - Or FederatedView                         │
│  - Or LogsView                              │
│  - Or SettingsView                          │
│                                             │
│  (Only one visible at a time)               │
│                                             │
├─────────────────────────────────────────────┤
│ Footer with keybindings (always visible)    │
│ [d] Dashboard [v] Devices [f] Federate      │
│ [l] Logs [s] Settings [q] Quit              │
└─────────────────────────────────────────────┘
```

## Screen Designs

### 1. Dashboard Screen (Main)
**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ Atlantico Federated Learning Server                    [?] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ Server Status ────────────────────────────────────┐    │
│  │ ● Running                Broker: mosquitto:1883    │    │
│  │ Connected Devices: 5     Round: 3/10               │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Quick Actions ───────────────────────────────────┐    │
│  │ [Start Federate] [Check Devices] [View Logs]      │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Recent Activity ─────────────────────────────────┐    │
│  │ 14:23:45 Device esp-001 joined                    │    │
│  │ 14:23:50 Round 3 started with 5 devices           │    │
│  │ 14:24:15 Device esp-002 training complete         │    │
│  │ 14:24:18 Device esp-003 training complete         │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [Dashboard] [Devices] [Federate] [Logs] [Settings] [Quit] │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Real-time server status (MQTT connection, device count)
- Current training round progress
- Quick action buttons
- Live activity feed (last 10 events)
- Navigation footer with tabs

### 2. Devices Screen
**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ Device Monitor                                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Check Alive] [Refresh]                Connected: 5/7     │
│                                                             │
│  ┌─ Connected Devices ───────────────────────────────┐    │
│  │ Device ID    │ Status  │ Last Seen  │ Round │ Acc │    │
│  ├──────────────┼─────────┼────────────┼───────┼─────┤    │
│  │ esp-001      │ ● Alive │ 2s ago     │ 3/10  │ 85% │    │
│  │ esp-002      │ ● Alive │ 1s ago     │ 3/10  │ 87% │    │
│  │ esp-003      │ ● Alive │ 3s ago     │ 3/10  │ 83% │    │
│  │ esp-004      │ ○ Dead  │ 45s ago    │ 2/10  │ 80% │    │
│  │ esp-005      │ ● Alive │ 1s ago     │ 3/10  │ 86% │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Device Details (esp-001) ────────────────────────┐    │
│  │ Status: Alive (connected 5m ago)                  │    │
│  │ Current Round: 3/10                               │    │
│  │ Epochs: 5 | Learning Rate: 0.0833                │    │
│  │ Accuracy: 85.2% | Loss: 0.342                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [Dashboard] [Devices] [Federate] [Logs] [Settings] [Quit] │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Real-time device table with status indicators
- Click device to see details in bottom panel
- Alive/Dead status with last seen timestamp
- Per-device training progress
- Check alive button to poll devices

### 3. Federated Learning Screen
**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ Federated Learning Control                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ Training Configuration ──────────────────────────┐    │
│  │ Rounds:          [10        ]  ← Current: 3       │    │
│  │ Epochs:          [5         ]                      │    │
│  │ Learning Rate:   [0.0833    ]                      │    │
│  │ Batch File:      [batch.json        ] [Browse]    │    │
│  │                                                     │    │
│  │ [Start Training] [Stop] [Pause/Resume]            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Training Progress ───────────────────────────────┐    │
│  │ Round 3 of 10                                      │    │
│  │ ██████████████████░░░░░░░░░░░░░░░░░░░░ 30%        │    │
│  │                                                     │    │
│  │ Devices: 5/5 completed                            │    │
│  │ Aggregation: In progress...                       │    │
│  │ Est. Time Remaining: 2m 15s                       │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Metrics ──────────────────────────────────────────┐    │
│  │ Global Accuracy: 85.4% (+2.1%)                    │    │
│  │ Global Loss: 0.328 (-0.045)                       │    │
│  │                                                     │    │
│  │ Round History:                                     │    │
│  │ R1: 78.2%  R2: 83.3%  R3: 85.4%                   │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [Dashboard] [Devices] [Federate] [Logs] [Settings] [Quit] │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Configuration inputs for training parameters
- Start/stop/pause controls
- Real-time progress bar
- Metrics display with history
- Batch file selection

### 4. Logs Screen
**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ System Logs                                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Filter: [All ▼] [INFO] [ERROR] [DEBUG]  [Clear] [Export] │
│                                                             │
│  ┌─ Log Stream ───────────────────────────────────────┐    │
│  │ [14:23:45] [INFO] MQTT broker connected            │    │
│  │ [14:23:50] [INFO] Device esp-001 joined            │    │
│  │ [14:23:52] [INFO] Device esp-002 joined            │    │
│  │ [14:24:00] [INFO] Starting federated round 3       │    │
│  │ [14:24:05] [DEBUG] Sent model to 5 devices         │    │
│  │ [14:24:15] [INFO] esp-002 training complete        │    │
│  │ [14:24:18] [INFO] esp-003 training complete        │    │
│  │ [14:24:20] [ERROR] esp-004 connection timeout      │    │
│  │ [14:24:25] [INFO] esp-001 training complete        │    │
│  │ [14:24:28] [INFO] Aggregating 4 device models      │    │
│  │ ...                                                 │    │
│  │                                                     │    │
│  │ [Auto-scroll: ON]                                  │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [Dashboard] [Devices] [Federate] [Logs] [Settings] [Quit] │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- Real-time log streaming
- Filter by level (INFO, ERROR, DEBUG)
- Auto-scroll toggle
- Export logs to file
- Color-coded by severity

### 5. Settings Screen
**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ Server Settings                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ MQTT Broker ──────────────────────────────────────┐    │
│  │ Host:      [mosquitto      ]                       │    │
│  │ Port:      [1883           ]                       │    │
│  │ Keepalive: [60             ] seconds               │    │
│  │                                                     │    │
│  │ [Test Connection] Status: ● Connected              │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Paths ────────────────────────────────────────────┐    │
│  │ Weights:  [weights/              ]                 │    │
│  │ Metrics:  [metrics/              ]                 │    │
│  │ Parse:    [parse/                ]                 │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Display ──────────────────────────────────────────┐    │
│  │ ☑ Debug mode                                       │    │
│  │ ☑ Show timestamps in logs                         │    │
│  │ ☐ Compact device view                             │    │
│  │ Refresh Rate: [1000        ] ms                    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  [Save Settings] [Reset to Defaults]                       │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [Dashboard] [Devices] [Federate] [Logs] [Settings] [Quit] │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- MQTT broker configuration
- Path settings
- Display preferences
- Test connection button
- Save/reset options

## Implementation Phases

### Phase 1: Setup and Skeleton (Tasks 4)
**Goal:** Get basic TUI running with navigation

1. Install Textual dependency
   ```bash
   pip install textual
   ```

2. Create TUI directory structure
   - Create `atlantico_server/tui/` folder
   - Create `__init__.py`, `app.py`
   - Create `screens/` and `widgets/` subfolders

3. Implement basic app structure
   - Create main `ServerApp` class inheriting from `textual.app.App`
   - Set up screen navigation (Dashboard, Devices, Federate, Logs, Settings)
   - Add footer with tab navigation
   - Add header with title

4. Create entry point
   - Create `server_tui.py` in root
   - Add command line argument to switch between CLI and TUI modes
   - Update `requirements.txt` with textual dependency

**Deliverable:** Running TUI app with empty screens and working navigation  
**Validation:** ✅ User feedback received - Phase 1 complete

### Phase 2: Dashboard Screen (Tasks 5a)
**Goal:** Implement main dashboard with server status

1. ✅ Create Dashboard screen layout
   - ✅ Simplified layout with title and device count
   - ✅ Quick action button (Start Test FL)
   - ✅ Recent activity panel with RichLog widget

2. ✅ Connect to MQTTFederatedServer
   - ✅ Pass server instance to TUI app
   - ✅ Display device count
   - ✅ Show connection status

3. ✅ Implement quick actions
   - ✅ Test FL button wired to federated learning
   - ✅ Runs in background thread (non-blocking)

4. ✅ Activity feed
   - ✅ Auto-tails last 10 lines from run/logs/server.log
   - ✅ Uses RichLog for proper formatting
   - ✅ Auto-refreshes every 0.5 seconds
   - ✅ Only updates when log file changes

**Deliverable:** ✅ Functional dashboard showing live server state  
**Validation:** ✅ User confirmed working! "It works! And it even has color!"

**Key Changes from Original Plan:**
- Simplified dashboard (removed ServerStatusPanel temporarily for testing)
- Activity feed reads from log file instead of maintaining separate event list
- Used RichLog widget for better formatting and color support

### Phase 3: Device Monitor Screen (Tasks 5b)
**Goal:** Real-time device status monitoring

1. ✅ Create device table widget
   - ✅ Two DataTable widgets: Training and Completed
   - ✅ Columns: Device, Round, Epochs, Samples, Accuracy, Loss
   - ✅ Color-coded states (🔄 Training, ✅ Done, 🏁 Completed)

2. ✅ Connect to server state
   - ✅ Read from optimized data structures (2 dicts instead of 4 arrays)
   - ✅ Auto-refresh every 1 second
   - ✅ Efficient state synchronization

3. ✅ Device progress tracking
   - ✅ Progress indicators: Training → Done → Completed
   - ✅ Real-time metric updates
   - ✅ Proper state transitions

4. ✅ Dual table layout
   - ✅ Top table: Active training devices
   - ✅ Bottom table: Completed devices
   - ✅ Auto-removes from training when done

**Deliverable:** ✅ Live device monitoring with dual tables  
**Validation:** ✅ User confirmed working after state optimization

### Phase 4: Federated Learning Screen (Tasks 5c)
**Goal:** Interactive training control

1. Configuration panel
   - Input fields for rounds, epochs, learning rate
   - File picker for batch configuration
   - Validation on inputs

2. Training controls
   - Start button calls `federate()` or `batch()`
   - Stop/pause functionality
   - Disable controls during training

3. Progress display
   - Progress bar for current round
   - Device completion counter
   - Time estimation

4. Metrics panel
   - Display accuracy, loss from results
   - Show round history (simple chart)
   - Calculate deltas from previous round

**Deliverable:** Full training control with live progress  
**Validation:** ⏳ Awaiting user feedback before proceeding to Phase 5

### Phase 5: Logs Screen (Tasks 5d)
**Goal:** Comprehensive log viewing

1. ✅ Log widget setup
   - ✅ Use RichLog widget (auto-scrolling)
   - ✅ Emoji icons for log levels (🔍 DEBUG, ℹ️ INFO, ⚠️ WARNING, ❌ ERROR, 🚨 CRITICAL)
   - ✅ Timestamp formatting [HH:MM:SS]

2. ✅ Logging integration
   - ✅ Created centralized atlantico_server/logging.py module
   - ✅ File-based logging to run/logs/server.log
   - ✅ TUI tails log file (no stdout capture)
   - ✅ Thread-safe logging from MQTT callbacks

3. ⏳ Filtering (Future)
   - ⏳ Buttons to filter by level
   - ⏳ Search functionality
   - ⏳ Clear logs button

4. ⏳ Export functionality (Future)
   - ✅ Logs already saved to file
   - ⏳ UI for choosing export location
   - ⏳ Copy to different destination

**Deliverable:** ✅ Complete log viewing with file tailing  
**Validation:** ✅ User confirmed working! Fixed double timestamp and stdout interference issues

**Key Architecture Decisions:**
- **File-based logging:** All logs written to run/logs/server.log
- **No stdout in TUI mode:** Prevents log pollution in dashboard (enable_stdout=False)
- **TUI tails file:** Logs screen reads file every 0.5s, shows new lines
- **Dashboard shows last 10:** Activity feed also tails file, displays last 10 lines
- **Clean separation:** One logging system, multiple display methods

### Phase 6: Settings Screen (Tasks 5e)
**Goal:** Configuration management

1. Settings form
   - Input fields for broker config
   - Path configuration
   - Display preferences

2. Validation
   - Input validation (port numbers, paths)
   - Test connection functionality
   - Error messages

3. Persistence
   - Save settings to config file
   - Load on startup
   - Reset to defaults option

4. Live updates
   - Apply settings without restart (where possible)
   - Reconnect broker if changed
   - Update display preferences immediately

**Deliverable:** Working settings management  
**Validation:** ⏳ Awaiting user feedback before proceeding to Phase 7

### Phase 7: Integration and Polish (Task 6)
**Goal:** Seamless integration with existing server code

1. Server lifecycle management
   - Start MQTT loop in background thread
   - Properly handle async operations
   - Clean shutdown on quit

2. Error handling
   - Catch exceptions in UI
   - Display user-friendly error messages
   - Prevent crashes

3. Responsive updates
   - Use Textual reactive variables
   - Efficient state synchronization
   - Debounce rapid updates

4. Styling
   - Create CSS file for consistent look
   - Add colors, borders, spacing
   - Dark theme (terminal-friendly)

5. Testing
   - Test all screens with real MQTT broker
   - Test with multiple devices
   - Verify state updates correctly

**Deliverable:** Production-ready TUI application  
**Validation:** ⏳ Awaiting final user feedback and acceptance

---

## Validation Process

**Important:** Each phase requires user feedback before proceeding to the next phase. The workflow is:

1. **Implement phase** - Complete all tasks for the current phase
2. **Present to user** - Show the working implementation
3. **Get feedback** - User tests and provides feedback
4. **Iterate if needed** - Make adjustments based on feedback
5. **Get approval** - User confirms phase is complete
6. **Move to next phase** - Only proceed after explicit approval

This ensures the TUI meets user expectations at each step and prevents building features that don't align with user needs.

---

## Technical Details

### Async Integration
Textual is fully async. The MQTTFederatedServer uses blocking MQTT client.

**Solution:**
- Keep MQTT `loop_start()` running in background thread (as currently designed)
- Use Textual's `call_from_thread()` to update UI from MQTT callbacks
- Use `run_worker()` for long-running operations (federate, batch)

Example:
```python
def _on_message(self, client, userdata, message):
    # In MQTT callback (different thread)
    data = message.payload.decode()
    if self.tui_app:
        self.tui_app.call_from_thread(self.tui_app.update_device_status, data)
```

### State Synchronization
Use Textual's reactive system to automatically update UI when state changes.

Example:
```python
from textual.reactive import reactive

class DeviceTable(Static):
    devices = reactive([])
    
    def watch_devices(self, devices):
        # Automatically called when devices list changes
        self.update_table(devices)
```

### Server Bridge
Create a thin bridge layer between MQTTFederatedServer and TUI:

```python
class ServerBridge:
    def __init__(self, server, app):
        self.server = server
        self.app = app
        self._setup_hooks()
    
    def _setup_hooks(self):
        # Hook into server events
        original_on_message = self.server._on_message
        def wrapped_on_message(*args, **kwargs):
            result = original_on_message(*args, **kwargs)
            self.app.call_from_thread(self.app.refresh_state)
            return result
        self.server._on_message = wrapped_on_message
```

## Docker Considerations

### Running TUI in Docker
Textual works in Docker but needs proper terminal setup:

1. Update `docker-compose.yml`:
   ```yaml
   atlantico-server:
     stdin_open: true  # Keep stdin open
     tty: true         # Allocate pseudo-TTY
     command: python server_tui.py  # Use TUI mode
   ```

2. Run with interaction:
   ```bash
   docker-compose run --rm atlantico-server
   ```

3. Fallback to CLI:
   - Add environment variable for mode selection
   - Use CLI mode in non-interactive containers
   - TUI mode for docker run/exec sessions

## Dependencies

Add to `requirements.txt`:
```
textual>=0.47.0
paho-mqtt>=1.6.1
numpy>=1.24.0
```

Textual has minimal dependencies and works with existing Python 3.11+.

## Success Criteria

✅ **Must Have:**
- [ ] All 5 screens implemented and navigable
- [ ] Real-time device status updates
- [ ] Working federated learning controls
- [ ] Live log streaming
- [ ] Settings persistence
- [ ] Graceful error handling
- [ ] Works in Docker with proper TTY setup

✅ **Nice to Have:**
- [ ] Keyboard shortcuts (Ctrl+D for devices, etc.)
- [ ] Help screen with command reference
- [ ] Export metrics to CSV
- [ ] Simple charts for accuracy trends
- [ ] Search in logs
- [ ] Device filtering/sorting

## Timeline Estimate

- Phase 1: 2-3 hours (setup, skeleton)
- Phase 2: 2-3 hours (dashboard)
- Phase 3: 3-4 hours (devices)
- Phase 4: 3-4 hours (federated learning)
- Phase 5: 2 hours (logs)
- Phase 6: 2 hours (settings)
- Phase 7: 2-3 hours (integration, polish)

**Total: ~16-22 hours**

## Next Steps

1. ✅ Review and approve this plan
2. Start Phase 1: Install Textual and create basic app structure
3. Iterate through phases, testing each one
4. Deploy and test in Docker environment
5. Gather feedback and iterate

---

**Ready to begin? Let's start with Phase 1!** 🚀
