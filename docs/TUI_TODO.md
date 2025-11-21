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
- ✅ System-wide logging refactoring
  - ✅ Converted 200+ Portuguese logs to English
  - ✅ Removed self._log() wrapper methods from server.py
  - ✅ Replaced all self._log() with self.logger.XXX
  - ✅ Removed emojis and redundant prefixes
  - ✅ Optimized log levels (DEBUG/INFO/WARNING/ERROR)
  - ✅ Integrated logger into reader.py (removed debug parameter)
  - ✅ Converted parser.py print() to logger calls
  - ✅ Fixed server_tui.py logger hierarchy (uses get_logger)
  - ✅ Committed: c51fdf3, 3b98eb8, 794b872

---

## Completed (Recently) ✅

### Phase 5.5: UI Architecture & Polish
**Completed:** November 2025  
**Effort:** ~6 hours

#### Architecture Changes ✅
- ✅ Converted from ContentSwitcher to Screen-based navigation
- ✅ Created CustomFooter with reactive highlighting of current view
- ✅ Dynamic header showing screen name
- ✅ CSS hot reload development setup (DEV_HOT_RELOAD.md, run_dev.sh)

#### CSS Organization ✅
- ✅ Created main.tcss (228 lines) - consolidated all inline CSS
- ✅ Created .panel utility class for consistent container styling
- ✅ Responsive dashboard layout with flexible activity feed
- ✅ Minimal dark theme with design tokens

#### Visual Polish ✅
- ✅ Button focus styling refined
- ✅ Border titles aligned left
- ✅ Prevented auto-focus on inputs
- ✅ Removed emoji panel titles for cleaner look

**Key Files Changed:**
- app.py, screens/*.py, styles/main.tcss, server_tui.py
- All *View classes renamed to *Screen

---

## In Progress ⏳

*No active work in progress - ready for Phase 6*

---

## Upcoming 📋

### Phase 5.6: Additional UI Polish
**Priority:** Medium  
**Estimated Effort:** 4-5 hours

#### Device Monitor Polish
- [ ] Improve table appearance
  - [ ] Better column widths
  - [ ] Alternate row colors (already done via CSS)
  - [ ] Status icons instead of text (● / ○)
- [ ] Add summary statistics panel
  - [ ] Total devices / Active / Inactive counts
  - [ ] Average accuracy across devices
  - [ ] Visual indicators
- [ ] Better state transitions
  - [ ] Smooth updates without flicker

#### Federated Learning Screen Polish
- [ ] Improve configuration panel
  - [ ] Better input field styling (already decent)
  - [ ] Input validation feedback (red border on invalid)
  - [ ] Help text for each field
- [ ] Enhance progress display
  - [ ] Styled progress bar with colors
  - [ ] Better round counter layout
  - [ ] Status badges instead of plain text
- [ ] Polish control buttons
  - [ ] Add icons/emojis to buttons (▶ ⏹ ⏸)
- [ ] Metrics panel improvements
  - [ ] Chart-like visual for history
  - [ ] Color-coded improvements/declines
  - [ ] Better number formatting (2 decimal places)

#### Logs Screen Polish
- [ ] Improve log display
  - [ ] Better syntax highlighting for log levels
  - [ ] Cleaner timestamp format
  - [ ] Level badges/pills instead of emojis
- [ ] Add filter UI
  - [ ] Level selector buttons (INFO/DEBUG/WARNING/ERROR)
  - [ ] Search input field
  - [ ] Clear/export buttons
- [ ] Better scrolling behavior
  - [ ] Auto-scroll toggle
  - [ ] Jump to top/bottom

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
- ✅ Empty server.log file (fixed logger hierarchy in server_tui.py)
- ✅ Portuguese logs throughout codebase (converted 200+ to English)
- ✅ Inconsistent logging patterns (unified to logger.XXX across all modules)

---

## Technical Debt 🔧

### High Priority
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
- [ ] Consider removing test FL button from dashboard
  - Proper Federated Learning screen implemented with full controls
  - Kept for backwards compatibility and quick testing

### Low Priority
- [ ] Add animations/transitions for screen changes
- [ ] Implement keyboard shortcuts help screen (?)
- [ ] Add system resource monitoring panel

---

## Changes Summary (November 2025)

### Architecture Refactor
1. **ContentSwitcher → Screen Navigation**
   - Removed ContentSwitcher, replaced with proper Screen-based architecture
   - Each view is now a Screen class with its own compose()
   - Header and CustomFooter docked in each screen
   - switch_screen() for navigation instead of ContentSwitcher.current

2. **File Structure Changes**
   - app.py: Added CustomFooter class, removed inline CSS, added update_header()
   - screens/*.py: Renamed *View → *Screen, added Header/Footer to compose()
   - screens/__init__.py: Updated exports to *Screen classes
   - styles/main.tcss: New organized stylesheet (228 lines)
   - DEV_HOT_RELOAD.md: New CSS hot reload documentation
   - run_dev.sh: New development script
   - server_tui.py: Added create_app() factory, app instance for textual run

3. **CSS Organization**
   - Consolidated all styles into main.tcss
   - Organized: Global → Layout → Base → Common → Utility → Screen-specific
   - Created .panel utility class for consistent container styling
   - Applied semantic design tokens ($surface, $panel, $text-muted, etc.)

4. **Visual Improvements**
   - Button focus: bold + underline + dark background
   - Border titles aligned left
   - Responsive dashboard with flexible activity feed
   - Footer highlights current screen in bold white
   - Header shows current screen name + "AILA Federated Framework"

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
- ✅ Phase 5 system-wide logging refactoring: "It's working"

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

**Last Updated:** November 15, 2025  
**Current Phase:** Phases 1-5.5 complete (including system-wide logging refactoring + UI architecture overhaul), ready for Phase 6 (Settings Screen)

### Recent Commits
- `c51fdf3` - refactor(server): modernize logging system and remove CLI menu
- `3b98eb8` - refactor(parser): convert print statements to logger calls
- `794b872` - refactor(tui): replace print statements with logger in server_tui.py
- **Pending** - refactor(tui): complete UI overhaul - Screen-based architecture, organized CSS, responsive layouts

---

## Change Summary (November 15, 2025)

### Architecture Refactor
- **ContentSwitcher → Screen Navigation:** Replaced ContentSwitcher with proper Screen-based architecture
- **All *View → *Screen:** Renamed all view classes to Screen classes
- **Docked Header/Footer:** Each screen now has docked Header and CustomFooter in its compose()
- **CSS Consolidation:** Moved all inline CSS (~530 lines) to single main.tcss (228 lines)

### New Features
- **CustomFooter:** Reactive footer highlighting current screen
- **Dynamic Header:** Shows "{screen_name} • AILA Federated Framework"
- **CSS Hot Reload:** Development setup with textual run --dev
- **.panel Utility Class:** Consistent styling across all containers

### Files Created
- styles/main.tcss (consolidated stylesheet)
- DEV_HOT_RELOAD.md (developer documentation)
- run_dev.sh (development launcher)

### Files Modified
- app.py, server_tui.py, all 5 screens, screens/__init__.py

**Result:** Cleaner architecture, organized CSS, better maintainability
