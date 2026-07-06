---
title: Ubuntu Hibernate Wizard
description: GTK4/libadwaita wizard for safely configuring Ubuntu hibernation with an existing active swap partition or swap file.
---

# Ubuntu Hibernate Wizard

Ubuntu Hibernate Wizard is a native GTK4/libadwaita desktop wizard for configuring Ubuntu hibernation with an **existing active persistent swap target**.

![Ubuntu Hibernate Wizard GTK4 menu screens](assets/screenshots/menu/00_contact_sheet_all_menu_steps.png)

Version **0.42.8** is intentionally conservative. It supports existing valid swap partitions/swap files and a controlled managed `/swap.img` create/resize flow. It does **not** repartition disks, change Secure Boot settings, or reboot the computer.

## What the wizard does

- Checks kernel hibernate support, Secure Boot/lockdown state, active swap, GRUB, initramfs-tools, and current resume configuration.
- Classifies swap partitions, swap files, zram, target size versus RAM, filesystem support, UUID, and swap-file resume offset.
- Recommends the safest existing hibernation target.
- Shows every planned file change before authentication.
- Applies changes through a narrow polkit helper.
- Creates rollback metadata before modification.
- Shows a text-only manual reboot notice after apply.

## Supported in v0.42

| Component | Current support |
|---|---|
| Desktop | Ubuntu/GNOME style desktop with GTK4 and libadwaita |
| Bootloader | GRUB only |
| Initramfs | initramfs-tools only |
| Swap partition | Existing active persistent partition with stable UUID and size >= RAM |
| Swap file | Existing active ext4 file with reliable offset, or btrfs file with `btrfs inspect-internal map-swapfile -r` |
| zram | Detected, but blocked as a hibernation target |
| Reboot | Manual notice only |

Unsupported or postponed: swap creation, swap resizing, inactive swap enabling, `/etc/fstab` swap management, systemd-boot, dracut, UKI, random-key encrypted swap, removable-media swap, and automatic reboot.

## Managed files

Real Apply may write only:

```text
/etc/initramfs-tools/conf.d/resume
/etc/default/grub.d/hibernate-wizard.cfg
```

The wizard does not blindly rewrite `/etc/default/grub` and does not edit arbitrary bootloader files.

## Start here

- [Install Ubuntu Hibernate Wizard](installation.md)
- [Use the wizard safely](usage.md)
- [See screenshots and examples](screenshots-and-examples.md)
- [Troubleshoot common hibernation problems](troubleshooting.md)
- [Understand the safety architecture](architecture.md)
