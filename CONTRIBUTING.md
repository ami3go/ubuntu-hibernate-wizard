# Contributing

Dev setup: Ubuntu 24.04+, `pip install pytest`, then `make test`.

Rules (from the engineering spec, see spec/):
1. **Tests first** for parsers and config editing — fixture-based, never touching the real system.
2. All privileged operations go through helper subcommands; never add sudo/pkexec calls in the GUI.
3. Any new user-facing error_code needs a docs/troubleshooting.md entry (CI checks this).
4. UI: GTK4 + libadwaita only, named style classes, no hard-coded colors.
