# Ubuntu Hibernate Wizard – Enable Hibernation on Ubuntu

![Ubuntu Hibernate Wizard banner](assets/banner.svg)

**Ubuntu Hibernate Wizard** is a GTK4/libadwaita app that helps you **enable, verify, and repair hibernation on Ubuntu** using a swap file, GRUB resume parameters, initramfs, systemd sleep configuration, and GNOME power-menu extension links.

It is built for common searches and real problems such as **Ubuntu hibernate not working**, `systemctl hibernate` not resuming, stale `resume_offset`, missing `resume=UUID=...`, and no Hibernate button in the GNOME power menu.

## What it does

- Checks Ubuntu, filesystem, swap, GRUB, initramfs, systemd, polkit, and Secure Boot state.
- Creates or resizes a swap file, including a custom swap size field.
- Calculates the correct `resume=UUID=...` and `resume_offset=...` for swap-file hibernation.
- Shows a reviewable plan before any privileged change.
- Updates `/etc/fstab`, GRUB resume configuration, systemd sleep settings, and polkit rules when needed.
- Rebuilds initramfs and guides you through reboot and verification.
- Saves a verbose timestamped log to `~/Downloads/hibernation_wizard_<timestamp>.log`.
- Links to GNOME Shell extensions that add Hibernate actions to the power menu.

## Start here

- [Installation](installation.md)
- [Usage guide](usage.md)
- [How Ubuntu hibernation works](how-hibernation-works.md)
- [Troubleshooting Ubuntu hibernation](troubleshooting.md)
- [Rollback and recovery](rollback-and-recovery.md)

## Safety model

Nothing runs without a reviewed plan. Every changed file is backed up. Every change can be rolled back. Verification does not trust old configuration: it recalculates UUID and swap-file offset from the current system state.
