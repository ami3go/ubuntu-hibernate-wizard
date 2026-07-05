# Rollback & Recovery

## Backups
Before any change: `/var/backups/ubuntu-hibernate-wizard/<timestamp>/` with a `manifest.json` recording each file's original state (or that it did not exist).

## One-click rollback
Available whenever an apply step fails, and from the menu afterwards. Files that existed are restored byte-for-byte; files the wizard created are removed; then `update-grub` and `update-initramfs` run again.

## Manual restore
```bash
sudo cp /var/backups/ubuntu-hibernate-wizard/<ts>/grub /etc/default/grub
sudo cp /var/backups/ubuntu-hibernate-wizard/<ts>/resume /etc/initramfs-tools/conf.d/resume
sudo update-grub && sudo update-initramfs -u -k all
```

## Resize crash recovery
Swap resize is journaled (`/var/lib/ubuntu-hibernate-wizard/resize-journal.json`). If the process is interrupted, the next start applies exactly one of these recoveries:

| Crash point | State on disk | Automatic recovery |
|---|---|---|
| While building | old swap intact | delete partial `.new`, restart resize |
| After swapoff, before rename | old file intact | reactivate old swap |
| After rename | new file complete | activate new file, continue |
| Before reconfigure | new swap active | recompute offset, re-offer config |

At no point can both files be lost.
