---
title: GUI object names
description: Stable GTK object names used by smoke tests and future UI automation.
---

# GUI object names

The GTK/libadwaita UI is built programmatically in Python for v0.42.8. GTK Builder XML is optional, not required, for this release. Programmatic UI is acceptable because business logic stays outside widget construction and critical widgets have stable names for smoke tests.

| Object name | Purpose |
|---|---|
| `app_window` | Main application window |
| `page_discovery` | Introduction/System Check page container |
| `page_swap_target` | Swap target selection page |
| `page_plan` | Planned modifications page |
| `page_apply` | Review & Apply page |
| `page_verify` | Finish/verification guidance page |
| `page_diagnostics` | Help/diagnostic guidance page |
| `runtime_diagram` | 8-step runtime diagram card |
| `btn_analyze` | Refresh/System Check action |
| `btn_apply` | Apply Plan action |
| `btn_export_diagnostics` | Diagnostic ZIP export action |
| `btn_rollback` | Rollback entry point/guidance |
| `btn_verify` | Verification entry point/guidance |
| `status_banner` | System status summary banner |
| `plan_summary` | Planned modifications summary |
| `blocker_list` | System check blocker/status list |
| `warning_list` | Target warnings/options list |

Changing these names requires updating the GTK smoke tests.
