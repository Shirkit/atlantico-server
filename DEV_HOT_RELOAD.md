# CSS Hot Reload Setup

To enable CSS hot reloading for TUI development:

## Using the dev script (recommended)

```bash
./run_dev.sh
```

This will:
1. Start the Textual console for debugging
2. Run the TUI with `textual run --dev` for hot CSS reload
3. Clean up on exit

## Manual setup

1. In one terminal, start the Textual console:
```bash
textual console
```

2. In another terminal, run the TUI with dev mode:
```bash
.venv/bin/textual run --dev atlantico_server/tui_runner.py:create_app
```

Now you can edit `atlantico_server/tui/styles/main.tcss` and changes will apply instantly without restarting!

## Notes

- The `--dev` flag is what enables CSS hot reload
- The `create_app()` factory function in `atlantico_server/tui_runner.py` is used instead of direct execution
- Do NOT use `python -m atlantico_server.tui_runner` directly - it won't enable hot reload
