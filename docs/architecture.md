---
title: Architecture and safety model
description: GTK4/libadwaita architecture, system probe, swap planner, polkit helper, managed files, rollback, and release gates for Ubuntu Hibernate Wizard.
---

# Architecture and safety model

Ubuntu Hibernate Wizard 0.42.8 uses a layered architecture so that the desktop GUI, planning logic, and privileged system changes remain separated.

## Layers

| Layer | Responsibility |
|---|---|
| GTK4/libadwaita GUI | Renders wizard pages, navigation, status, logs, screenshots, and user choices. |
| System probe | Reads current system facts without root where possible. |
| Swap classifier | Classifies existing active swap partitions/files and blocks unsafe targets. |
| Planner | Builds a reviewable plan with exact managed files and commands. |
| Privileged helper | Revalidates the live system and applies only allowlisted changes through polkit. |
| Rollback manager | Records pre-change metadata and restores/removes wizard-managed files only when safe. |

## v0.42 scope

Only existing active swap partition/file targets are supported. Swap creation, resizing, `/etc/fstab` swap management, formatting, repartitioning, inactive swap enabling, Secure Boot changes, and automatic reboot are out of scope.

## Helper protocol

Real apply uses:

```text
pkexec /usr/libexec/ubuntu-hibernate-wizard/ubuntu-hibernate-wizard-helper --action apply-plan --stdin-json
```

The helper validates:

- protocol version and application version;
- action and dry-run mode;
- selected target kind/path/UUID/offset;
- planned step IDs;
- managed file paths;
- duplicate steps or files;
- unknown fields;
- live system classification.

It uses fixed command arrays and never executes arbitrary shell strings.

## Managed files

The helper may write only:

```text
/etc/initramfs-tools/conf.d/resume
/etc/default/grub.d/hibernate-wizard.cfg
```

It then runs:

```text
update-initramfs -u
update-grub
```


## UI structure decision

The v0.42.8 GTK/libadwaita UI is built programmatically in Python. GTK Builder XML remains optional, not mandatory, for this release. This is intentional: the business logic is kept in service/controller modules, while the GUI assigns stable object names to critical widgets for smoke tests and future UI automation. See `gui-object-names.md`.

## Static safety checks

CI includes static safety tests that fail if active code directly writes protected configuration such as `/etc/fstab` or `/etc/default/grub`, or if dangerous commands bypass the reviewed helper/command path. Legacy swap creation/resizing remains out of the normal v0.42 flow.

## Diagnostic ZIP

The GUI exports a structured diagnostic ZIP, not a loose text file. The bundle includes a manifest, summary, swap-detection JSON, bounded command snapshots, redacted config snapshots, rollback context, and UI state. It redacts user paths, hostnames, machine-id, private-key material, tokens, and unrelated serials where practical.

## Release gates

| Gate | Meaning | Current package status |
|---|---|---|
| Gate A | GTK4 GUI shell and pages | Passed |
| Gate B | Fake-system planner and swap classifier | Passed |
| Gate C | Dry-run apply | Passed |
| Gate D | Helper hardening | Passed |
| Gate E | Disposable Ubuntu VM real apply | Tooling implemented, real VM validation pending |
| Gate F | Release-candidate evidence check | Tooling implemented, evidence pending |

Do not treat the package as a public real-apply release until Gate E and Gate F evidence are complete.
