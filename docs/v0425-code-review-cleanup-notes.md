# v0.42.5 Code Review Cleanup Notes

This update reviews and hardens the v0.42.4 Gate F source package before further release-gate work.

## Fixed

- Removed the stale duplicate `helper/` source tree. The packaged helper source is now only `ubuntu_hibernate_wizard/backend/privileged_helper.py`.
- Removed unreachable helper methods left from older swap creation/resizing flows:
  - `cmd_update_fstab`
  - `cmd_update_sleep_conf`
  - `cmd_update_polkit_rule`
  - `cmd_resize_swap`
  - unused `_probe_swap_details`
  - unused `_cleanup_side_file`
- Removed unused rollback helpers that were no longer called after v0.42 scope was frozen to existing active swap targets only.
- Reworked CLI `--verify` to use the same `system_probe` + `classify_swap_targets` path as the GUI instead of duplicating swap-file offset parsing.
- Removed stale version constants and aligned `APP_VERSION`, `__version__`, `pyproject.toml`, Debian packaging, README, AppStream metadata, and changelogs to 0.42.5.
- Made generated GRUB fragments idempotent using a small shell helper, so the wizard appends missing `resume=` / `resume_offset=` tokens without duplicating matching tokens already present in `GRUB_CMDLINE_LINUX_DEFAULT`.
- Strengthened one-shot helper request validation:
  - rejects mismatched app versions;
  - requires `dry_run` to be boolean;
  - validates rollback mode;
  - rejects duplicate planned files and duplicate step IDs;
  - rejects unknown fields inside `selected_target`;
  - validates selected target UUID syntax;
  - validates active target boolean state.
- Removed unused Gate E hostname helper.
- Added tests for stricter helper schema validation and updated golden GRUB fragment tests.

## Validation

```text
76 passed
make deb completed
Built dist/ubuntu-hibernate-wizard_0.42.5-1_all.deb
```

## Remaining release boundary

This package is still not marked Gate E/Gate F passed. Real privileged apply and manual hibernate/resume validation still require a disposable Ubuntu VM.
