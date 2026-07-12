---
title: Ubuntu Hibernate Wizard
description: GTK4/libadwaita wizard for safely configuring Ubuntu hibernation with an existing active swap partition or swap file.
---

# Ubuntu Hibernate Wizard

Ubuntu Hibernate Wizard is a native GTK4/libadwaita desktop wizard for configuring Ubuntu hibernation with an **existing active persistent swap target**.

![Ubuntu Hibernate Wizard real GTK4 menu screens](assets/screenshots/menu/00_contact_sheet_all_menu_steps.png)

These screenshots are captured from a real Ubuntu desktop running the application.

Version **0.4.3 RC6** is a real-system-tested release candidate. It supports existing valid swap partitions/swap files and a controlled managed `/swap.img` create/resize flow. It does **not** repartition disks, change Secure Boot settings, or reboot the computer.

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
