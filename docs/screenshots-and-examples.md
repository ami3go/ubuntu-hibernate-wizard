---
title: Screenshots and examples
description: GTK4 Ubuntu Hibernate Wizard screenshots, planned modification examples, dry-run logs, verification commands, and rollback preview examples.
---

# Screenshots and examples

These real screenshots show the Ubuntu Hibernate Wizard 0.4.3 RC4 GTK4/libadwaita workflow running on an Ubuntu desktop: check the system, choose an existing swap target or managed `/swap.img`, review managed file changes, apply through the helper, and reboot manually.

## Complete menu overview

![Ubuntu Hibernate Wizard menu overview](assets/screenshots/menu/00_contact_sheet_all_menu_steps.png)

## Introduction

The start page explains the release-candidate scope and shows the application banner and main wizard capabilities.

![Ubuntu Hibernate Wizard introduction screen](assets/screenshots/menu/01_introduction.png)

## System Check

System Check probes the host without starting a privileged helper. It checks active swap, GRUB, initramfs-tools, Secure Boot/lockdown, and existing resume configuration.

![Ubuntu Hibernate Wizard system check screen](assets/screenshots/menu/02_system_check.png)

## Configuration

The Configuration page lists existing active swap targets and can also prepare a managed `/swap.img` using RAM-based presets or manual size input.

![Ubuntu Hibernate Wizard configuration screen](assets/screenshots/menu/03_configuration.png)

## Planned modifications

The plan shows a compact status table, compact planned-change table, and expandable technical details before authentication.

![Ubuntu Hibernate Wizard planned modifications screen](assets/screenshots/menu/04_planned_modifications.png)

Example plan for an existing ext4 swap file:

```text
1. Re-check selected hibernation target: /swap.img, ext4, offset 5986304
2. Create rollback metadata before file writes
3. Write /etc/initramfs-tools/conf.d/resume
4. Write /etc/default/grub.d/hibernate-wizard.cfg
5. Run update-initramfs -u
6. Run update-grub
```

## Review and Apply

Dry-run mode is safe and does not write files. Real apply streams structured helper events.

![Ubuntu Hibernate Wizard review and apply screen](assets/screenshots/menu/05_review_apply.png)

Example dry-run excerpt:

```text
[12:03:01] Dry-run mode: no system files will be written and no commands will be executed
[12:03:02] Selected swap target: /swap.img
[12:03:03] Allowed managed files: /etc/initramfs-tools/conf.d/resume, /etc/default/grub.d/hibernate-wizard.cfg
[12:03:04] Dry-run step 5/6: Run update-initramfs -u
[12:03:05] Dry-run step 6/6: Run update-grub
```

## Finish

The Finish page tells the user to reboot manually, provides read-only post-restart verification with a live status window, and offers optional GNOME hibernate menu extension links.

![Ubuntu Hibernate Wizard finish screen](assets/screenshots/menu/06_finish.png)

## Help and About

![Ubuntu Hibernate Wizard help screen](assets/screenshots/menu/07_help.png)

![Ubuntu Hibernate Wizard about screen](assets/screenshots/menu/08_about.png)

## Verify after reboot

```bash
ubuntu-hibernate-wizard --verify
```

Useful support commands:

```bash
swapon --show --bytes
cat /proc/cmdline
cat /etc/initramfs-tools/conf.d/resume
cat /etc/default/grub.d/hibernate-wizard.cfg
```

For swap files:

```bash
findmnt -no SOURCE,FSTYPE,UUID -T /swap.img
sudo filefrag -v /swap.img | awk '$1=="0:" {print $4}'
```

For btrfs swap files:

```bash
sudo btrfs inspect-internal map-swapfile -r /swap.img
```

## Rollback preview

Rollback is manifest-backed and conservative. It restores/removes only files that the snapshot proves are safe.

```bash
ubuntu-hibernate-wizard --list-rollbacks
ubuntu-hibernate-wizard --preview-rollback 20260705-180000-a1b2c3
```

Example output:

```text
Rollback preview for 20260705-180000-a1b2c3
1. will-run: restore-file /etc/default/grub.d/hibernate-wizard.cfg
2. will-run: remove-created-file /etc/initramfs-tools/conf.d/resume
```
