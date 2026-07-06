---
title: Diagnostic ZIP export
description: What Ubuntu Hibernate Wizard includes in diagnostic ZIP bundles and what is redacted for privacy.
---

# Diagnostic ZIP export

Ubuntu Hibernate Wizard exports support information as a structured ZIP bundle, not as a loose text file.

The filename format is:

```text
ubuntu-hibernate-wizard-diagnostics-YYYYMMDD-HHMMSS.zip
```

Typical contents:

```text
manifest.json
summary.txt
app.log
system-info.txt
swap-detection.json
swap-detection.txt
commands/proc-swaps.txt
commands/proc-meminfo.txt
commands/lsblk.json
commands/swapon-show.txt
commands/findmnt.json
commands/dmsetup-info.txt
configs/fstab.redacted.txt
configs/crypttab.redacted.txt
configs/grub.redacted.txt
rollback/rollback-plan.json
rollback/rollback-summary.txt
ui/wizard-state.json
```

## Privacy policy

The diagnostic bundle is intentionally narrow. It does not recursively scan the home directory and does not include unrelated user files.

Redaction removes or avoids:

- usernames in `/home/<user>` style paths;
- hostnames where practical;
- `/etc/machine-id`;
- private keys;
- token/API-key/password-like strings;
- unrelated disk serial numbers.

Swap and resume-relevant UUIDs may be present because they are needed to troubleshoot hibernation target selection. Unrelated disk identifiers should not be included.

## Failure behavior

If one diagnostic command is unavailable or fails, export should still produce a ZIP. The failure is represented in the relevant file instead of crashing the application.

## v0.42.8 diagnostic privacy update

Public diagnostic ZIP exports redact filesystem and swap UUID-like identifiers by default. This is intentional because UUIDs can identify a specific machine or disk layout. A deterministic `fixture-summary.txt` is included only when exporting fake-system fixtures for automated tests.
