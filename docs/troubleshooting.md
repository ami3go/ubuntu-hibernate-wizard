---
title: Troubleshooting Ubuntu hibernation
description: Fix common Ubuntu hibernation problems involving zram, swap size, resume UUID, resume_offset, GRUB, initramfs-tools, Secure Boot, and conflicting configuration.
---

# Troubleshooting

This page lists the most common reasons Ubuntu hibernation setup is blocked or fails to resume.

## zram only

zram cannot survive power-off, so it cannot store the hibernation image. The wizard blocks zram as a hibernation target.

Fix: create and enable a persistent disk-backed swap partition or swap file manually, then rerun the wizard.

## No active swap

v0.42 supports existing active swap targets and managed `/swap.img` create/resize. It does not repartition disks or reboot automatically.

Check:

```bash
swapon --show --bytes
```

## Swap smaller than RAM

The selected target must be large enough to store the hibernation image. v0.42 blocks Apply when the selected target is smaller than RAM.

## Swap file without reliable offset

For a swap file, the kernel needs `resume_offset`. On ext4, the wizard uses `filefrag`. On btrfs, it accepts only the value returned by:

```bash
sudo btrfs inspect-internal map-swapfile -r /swap.img
```

If the offset cannot be trusted, Apply is blocked.

## Non-GRUB system

v0.42 supports GRUB + initramfs-tools only. systemd-boot, dracut, UKI, and custom boot stacks are out of scope.

Check:

```bash
command -v update-grub
command -v update-initramfs
```

## Conflicting resume parameters

Existing `resume=`, `resume_offset=`, or `RESUME=` values that point to a different target can cause cold boot instead of resume.

The wizard blocks Apply until the conflict is reviewed. It must not create duplicate resume parameters.

## Secure Boot or kernel lockdown

Secure Boot and kernel lockdown can prevent hibernation on some systems. The wizard detects and warns, but it does not change Secure Boot settings.

## System hibernates but cold-boots instead of resuming

Check these values after reboot:

```bash
cat /proc/cmdline
cat /etc/initramfs-tools/conf.d/resume
swapon --show --bytes
```

Common causes:

- stale `resume=UUID=...` value;
- wrong swap-file `resume_offset`;
- initramfs not regenerated after configuration changes;
- GRUB not regenerated after kernel parameter changes;
- encrypted storage not available early enough in boot.

## Need support

Use the GUI **Export Diagnostic Report** action where available, or collect:

```bash
ubuntu-hibernate-wizard --verify
swapon --show --bytes
cat /proc/cmdline
cat /etc/initramfs-tools/conf.d/resume
cat /etc/default/grub.d/hibernate-wizard.cfg
```

Do not paste unrelated full `/etc/fstab` or private host/user names unless needed.
