# Atlantico Server TUI - TODO List

## Current Status: Phases 1-5 Complete ✅

### Completed ✅

#### Phase 1: Setup and Skeleton
- ✅ Install Textual dependency (>=0.47.0)
- ✅ Create TUI directory structure (tui/, screens/, widgets/)
- ✅ Implement ContentSwitcher architecture
- ✅ Add header and footer with keybindings
- ✅ Create server_tui.py entry point

#### Phase 2: Dashboard
- ✅ Simple dashboard layout with device count
- ✅ Test FL button for federated learning
- ✅ Activity feed with RichLog widget
- ✅ Auto-tail last 10 log lines from file
- ✅ Background thread for FL (non-blocking UI)

#### Phase 3: Device Monitor
- ✅ Dual DataTable layout (Training/Completed)
- ✅ Progress states: Training → Done → Completed
- ✅ Real-time metrics display
- ✅ Auto-refresh every 1 second
- ✅ Optimized data structures (2 dicts)

#### Phase 4: Federated Learning Control
- ✅ Configuration panel with 4 input fields (rounds, epochs, clients, batch)
- ✅ Training control buttons (Start, Stop, Pause/Resume)
- ✅ Start button wired to federated learning
- ✅ Background thread execution (non-blocking)
- ✅ Dynamic button states (disabled when idle, enabled when training)
- ✅ Pause/Resume functionality
  - ✅ Server continues aggregation when paused
  - ✅ Holds aggregated weights until resume
  - ✅ Button changes label and color dynamically
  - ✅ Progress panel shows pause status
- ✅ Progress display
  - ✅ Progress bar for current round
  - ✅ Round counter display
  - ✅ Connected device count
  - ✅ Training status with pause indicator
  - ✅ Auto-refresh every 1 second
- ✅ Metrics panel structure (ready for data)
- ✅ Stop button (graceful shutdown)
  - ✅ Sends unsubscribe command to devices
  - ✅ Stops batch processing loop
  - ✅ Stops training loop with proper cleanup
  - ✅ Works during pause state
  - ✅ 6 strategic checkpoints for responsiveness
- ⏳ Wire metrics to actual training data - TODO

#### Phase 5: Logging System
- ✅ Created centralized logging.py module
- ✅ EmojiFormatter with level icons
- ✅ File-based logging (run/logs/server.log)
- ✅ TUI tails log file (no stdout capture)
- ✅ Thread-safe logging from MQTT callbacks
- ✅ Separate CLI/TUI modes (enable_stdout parameter)
- ✅ Fixed double timestamp issue
- ✅ Fixed log pollution in dashboard

---

## In Progress ⏳

*No active work in progress - ready for Phase 6*

---

## Upcoming 📋

### Phase 6: Settings Screen
**Priority:** Medium  
**Estimated Effort:** 2-3 hours

Tasks:
- [ ] MQTT Broker configuration
  - [ ] Host input field
  - [ ] Port input field (with validation)
  - [ ] Keepalive setting
  - [ ] Test Connection button
- [ ] Path configuration
  - [ ] Weights folder path
  - [ ] Metrics folder path
  - [ ] Parse folder path
- [ ] Display preferences
  - [ ] Debug mode toggle
  - [ ] Show timestamps toggle
  - [ ] Refresh rate slider
- [ ] Save/Reset functionality
  - [ ] Save to config file
  - [ ] Load on startup
  - [ ] Reset to defaults button

**Dependencies:** None  
**Notes:** Could use Textual forms or manual input validation

### Phase 7: Integration and Polish
**Priority:** High (before release)  
**Estimated Effort:** 3-4 hours

Tasks:
- [ ] Error handling
  - [ ] Catch exceptions in UI updates
  - [ ] Display user-friendly error modals
  - [ ] Prevent TUI crashes
  - [ ] Log errors to file
- [ ] Responsive updates optimization
  - [ ] Debounce rapid state changes
  - [ ] Use reactive variables efficiently
  - [ ] Minimize full-table refreshes
- [ ] Styling improvements
  - [ ] Create consistent color scheme
  - [ ] Improve borders and spacing
  - [ ] Better visual hierarchy
  - [ ] Dark theme optimization
- [ ] Performance testing
  - [ ] Test with real MQTT broker
  - [ ] Test with 10+ devices
  - [ ] Check memory usage over time
  - [ ] Verify state sync accuracy
- [ ] Documentation
  - [ ] Update README with TUI instructions
  - [ ] Add keybindings reference
  - [ ] Docker setup guide
  - [ ] Troubleshooting section

**Dependencies:** All other phases complete  
**Notes:** This is the final polish before production

---

## Bugs & Issues 🐛

### Active Issues
*No active issues*

### Fixed Issues
- ✅ Double timestamps in logs (removed timestamp from TUILogHandler)
- ✅ Dashboard showing all server logs (disabled stdout in TUI mode)
- ✅ MQTT logs not appearing (created _log() method with log_capture)
- ✅ Device monitor state confusion (optimized to 2 dicts with computed properties)

---

## Technical Debt 🔧

### High Priority
- [x] Remove temporary test FL button from dashboard
  - ✅ Proper Federated Learning screen implemented with full controls
  - ⏳ TODO: Remove test button from dashboard (kept for backwards compatibility)
- [x] Implement Stop button functionality
  - ✅ Stop button sends unsubscribe command to devices
  - ✅ Graceful shutdown with proper cleanup
  - ✅ Multiple checkpoints throughout execution flow
- [ ] Wire metrics panel to actual training data
  - Structure exists, needs data from aggregation results
  - Calculate accuracy and loss from device models
  - Show round history
- [ ] Restore ServerStatusPanel on dashboard
  - Was removed for testing
  - Re-enable once widget refresh issues resolved
- [ ] Add proper error handling in device monitor
  - Handle missing device data gracefully
  - Show error states in table

### Medium Priority
- [ ] Implement log filtering in Logs view
  - Filter by level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - Search functionality
  - Clear logs button
- [ ] Add export functionality for logs
  - UI for choosing export location
  - Copy to different destination with timestamp
- [ ] Optimize log file reading
  - Currently reads entire file every 0.5s
  - Could use file seeking to read only new lines
  - Add max file size handling

### Low Priority
- [ ] Add keyboard shortcuts
  - Ctrl+D → Devices
  - Ctrl+L → Logs
  - Ctrl+F → Federated
  - Ctrl+S → Settings
- [ ] Add help screen
  - Show all keybindings
  - Explain each view
  - Quick start guide
- [ ] Add simple charts for metrics
  - Accuracy trend over rounds
  - Loss trend
  - Device participation

---

## Future Enhancements 💡

### Nice to Have
- [ ] Device filtering and sorting in Device Monitor
  - Sort by ID, status, accuracy
  - Filter by alive/dead
  - Search by device ID
- [ ] Export device metrics to CSV
  - All devices or selected
  - Include timestamps
  - Configurable columns
- [ ] Training history viewer
  - Show past training runs
  - Compare runs
  - Export comparison data
- [ ] Real-time charts
  - Live accuracy graph during training
  - Device status pie chart
  - Round progress timeline
- [ ] Multi-broker support
  - Connect to multiple brokers
  - Switch between environments
  - Aggregate metrics

### Ideas from Users
*Add user feedback and suggestions here*

---

## Notes & Decisions 📝

### Architecture Decisions
1. **ContentSwitcher over Screen Navigation:** Chosen for persistent header/footer and faster view switching
2. **File-based logging:** All logs to file, TUI tails it. Cleaner than stdout capture
3. **No stdout in TUI mode:** Prevents log pollution in dashboard and other widgets
4. **Dual-table device monitor:** Separates active training from completed devices for clarity
5. **Background threads for FL:** Prevents UI freeze during long operations

### Performance Considerations
- Log file is cleared on startup (mode='w') to prevent unbounded growth
- Device monitor updates every 1s (not too frequent)
- Activity feed only updates when log line count changes
- Full table refresh on state change (could optimize later)

### User Feedback
- ✅ User confirmed Phase 1 working: "Perfect skeleton!"
- ✅ User confirmed Phase 2 working: "It works! And it even has color!"
- ✅ User confirmed Phase 3 working after optimization
- ✅ User confirmed logging working: "Nice, much much better"
- ✅ Phase 4 implementation complete: Pause/resume functionality working

---

## Quick Reference

### Current File Structure
```
atlantico-server/
├── atlantico_server/
│   ├── server.py (modified for logging)
│   ├── logging.py (NEW - centralized logging)
│   └── tui/
│       ├── app.py (main TUI app)
│       ├── screens/
│       │   ├── dashboard.py (Phase 2 ✅)
│       │   ├── devices.py (Phase 3 ✅)
│       │   ├── logs.py (Phase 5 ✅)
│       │   ├── federated.py (Phase 4 🔜)
│       │   └── settings.py (Phase 6 📋)
│       └── widgets/ (empty for now)
├── server_tui.py (TUI entry point)
└── docs/
    ├── TUI_IMPLEMENTATION_PLAN.md (updated)
    └── TUI_TODO.md (this file)
```

### Key Commands
- Run TUI: `.venv/bin/python server_tui.py`
- View logs: Press `l` in TUI
- View devices: Press `v` in TUI
- Dashboard: Press `d` in TUI
- Quit: Press `q` in TUI

### Important Environment Variables
- `ATLANTICO_SERVER_LOG`: Path to log file (default: run/logs/server.log)

---

**Last Updated:** November 14, 2025  
**Current Phase:** Phases 1-5 complete + Stop functionality, ready for Phase 6 (Settings Screen)
