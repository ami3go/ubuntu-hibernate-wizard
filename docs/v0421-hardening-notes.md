# v0.42.1 GTK4 Hardening Notes

This update addresses the v0.42 readiness review findings without expanding the release scope.

## Scope kept unchanged

v0.42.1 still supports existing active swap partition/file targets only. It does not create swap, resize swap, enable inactive swap, edit `/etc/fstab`, change Secure Boot, or reboot automatically.

## Implemented fixes

- System Check uses an unprivileged read-only probe and no longer starts a pkexec helper during normal detection.
- Real Apply still uses the one-shot privileged helper and the helper re-probes/reclassifies the live system before writing files.
- The GUI loads bundled original SVG assets instead of GNOME symbolic theme icons.
- Planned Modifications includes the required apply-phase and runtime hibernation diagrams.
- Diagnostic export is available from the GUI and applies redaction for home paths, hostnames, and unrelated full fstab content.
- btrfs swap files are blocked unless `btrfs inspect-internal map-swapfile -r` returns a numeric kernel `resume_offset`.
- encrypted swap is blocked unless a stable initramfs-available mapping is explicitly proven.
- The one-shot helper rejects unknown top-level fields, missing managed files, missing required steps, unknown actions, and unsafe file targets.
- `rollback-files` is implemented in the one-shot helper path.
- Added tests for bootloader tooling detection, encrypted swap, btrfs offset policy, helper schema rejection, bundled-icon usage, diagnostic redaction, and exact golden config output.

## Validation

```text
python3 -m pytest -q
66 passed

make deb
Built dist/ubuntu-hibernate-wizard_0.42.1-1_all.deb
```

Real privileged Apply was not executed in this environment. Keep the disposable Ubuntu VM gate before enabling release builds for general users.
