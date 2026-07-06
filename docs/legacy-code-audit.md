---
title: Legacy code audit
description: v0.42.8 legacy fstab and swap-resize code audit and active-scope decision.
---

# Legacy code audit

v0.42.8 keeps the active public flow narrow: existing active disk swap targets plus controlled managed `/swap.img` create/resize.

| Area | Decision | Notes |
|---|---|---|
| `/etc/fstab` swap management | Disabled from active v0.42 flow | Older parser helpers may remain for compatibility tests, but Apply does not manage fstab swap entries. |
| Swap creation | Out of scope | No automatic create/format path. |
| Swap resizing | Out of scope | Resize helper commands are rejected by hardened helper tests. |
| Inactive swap enablement | Out of scope | User must enable persistent swap manually before using the wizard. |
| GRUB rewrite | Isolated | The app writes a managed GRUB fragment, not arbitrary `/etc/default/grub` edits. |
| initramfs resume config | Active | Written only through reviewed helper/rollback path. |
| Rollback | Active | File backup/rollback metadata is maintained before writes. |

Static safety tests guard against direct protected-file writes or dangerous command bypasses outside approved helper/rollback modules.

## v0.42.8 public helper surface decision

The persistent JSONL helper no longer accepts legacy mutating commands such as `begin-operation`, `finish-operation`, `update-grub-resume`, `update-initramfs-resume`, or rollback swap-cleanup commands. Those method bodies remain only as private compatibility/dead-code review context, but they are not listed in `MUTATING` and cannot be reached through the public persistent helper protocol. Public apply remains limited to the one-shot `apply-plan` helper action, which re-probes the live target before any managed-file write.
