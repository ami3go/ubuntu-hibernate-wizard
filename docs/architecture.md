# Architecture

```
┌────────────────────────┐   JSON Lines (stdin/stdout)   ┌──────────────────────────┐
│  GUI (GTK4/libadwaita) │ ────────────────────────────► │ privileged-helper (root) │
│  unprivileged          │ ◄──────────────────────────── │ launched ONCE via pkexec │
└────────────────────────┘   responses + progress events └──────────────────────────┘
```

- **One elevation per run**: the helper is a session process; the GUI gets progress streaming for long operations.
- **Plan-token gating**: the helper refuses any mutating subcommand not registered by `submit-plan` — the on-screen dry-run is enforced, not advisory.
- **No generic exec**: the helper exposes a fixed subcommand set; there is no "run this command" API.
- **Parsers are the foundation**: `swapon`, `findmnt`, `filefrag`, cmdline output is parsed with strict, fixture-tested parsers under `LC_ALL=C`; invalid output aborts rather than guessing.
- Modules: `core/parsers.py`, `core/grub.py`, `core/system.py` (fstab/verify/journal/backup), `backend/privileged_helper.py`, `backend/session.py`, `state/state_manager.py`, `cli.py`, `ui/wizard_window.py`.
