---
title: v0.42 production hardening notes
description: Release-candidate hardening notes for Ubuntu Hibernate Wizard v0.42.x.
---

# v0.42 production hardening notes

v0.42.8 adds public-use hardening before Release Candidate tagging.

## Added

- Structured fake-system fixtures under `tests/fixtures/fake_systems/`.
- Golden expected outputs for swap targets, blockers, warnings, plan, and diagnostic summaries.
- Conservative encrypted swap classification using `/etc/crypttab`, mapper paths, `lsblk`, and `dmsetup` evidence.
- Diagnostic ZIP export with manifest, summary, swap detection JSON, command snapshots, redacted config snapshots, rollback context, and wizard state.
- GTK smoke tests prepared for Ubuntu CI with `python3-gi`, GTK4, libadwaita, Xvfb, and system Python.
- Static safety tests to guard against direct protected-file writes and dangerous command bypasses.
- Stable GTK object names for future UI automation.
- Complete 8-step runtime diagram and documented read/write touchpoints.

## Conservative blocking behavior

These systems are blocked from automatic hibernation configuration in v0.42.x:

- zram-only swap;
- swap smaller than RAM;
- encrypted swap with random key or `swap` crypttab option;
- unknown `/dev/mapper/*` swap backing;
- persistent encrypted swap without explicitly implemented/tested safe resume path;
- malformed or ambiguous configuration where safe behavior cannot be proven.

## Still out of scope

- Swap creation or resizing.
- Inactive swap enablement.
- Partition formatting or repartitioning.
- systemd-boot, dracut, UKI, and non-GRUB stacks.
- Automatic reboot button.
- Automatic encrypted-hibernation setup.
