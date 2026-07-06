---
title: Ubuntu Hibernate Wizard FAQ
description: Answers about Ubuntu hibernation, swap files, swap partitions, zram, btrfs, Secure Boot, LUKS, rollback, verification, and GNOME hibernate buttons.
---

# FAQ

## Does Ubuntu support hibernation with a swap file?

Yes, but the boot configuration must point to the backing filesystem UUID and the physical swap-file offset. The wizard calculates and verifies both values for supported filesystems.

## Is a swap partition easier than a swap file?

Usually yes. A swap partition only needs a stable resume identifier such as `resume=UUID=...`. A swap file also needs `resume_offset=...`.

## Why does Ubuntu hibernate but not resume?

The most common cause is stale boot configuration. If `resume=UUID=...` or `resume_offset=...` no longer matches the real swap target, the system cold-boots instead of restoring the hibernated image.

## Does the wizard create or resize swap?

Yes, v0.42.12 can create or resize the managed `/swap.img` file using the reviewed helper/plan/rollback flow. It still does not repartition disks, format swap partitions, change Secure Boot settings, or reboot automatically.

## Is zram enough for hibernation?

No. zram is useful for runtime compression, but it does not survive power-off. Hibernation needs a persistent disk-backed swap partition or swap file.

## What about Secure Boot?

Secure Boot and kernel lockdown may block hibernation on some Ubuntu systems. The wizard detects and warns, but it does not modify Secure Boot settings.

## What about encrypted disk or LUKS?

Encrypted installations need extra handling because early boot must unlock the storage before the hibernation image can be read. Random-key encrypted swap is blocked. Stable initramfs-available encrypted mappings must be explicitly proven before they can be considered safe.

## What about btrfs?

A btrfs swap file is accepted only when this command returns a reliable numeric resume offset:

```bash
sudo btrfs inspect-internal map-swapfile -r <swapfile>
```

No `filefrag` fallback is used for btrfs.

## Does the app reboot my system?

No. Current versions show a text-only manual reboot notice. Reboot from the system menu when ready.

## Does installing the `.deb` change boot configuration?

No. Installing the package installs the app, desktop launcher, polkit policy, helper, and documentation. Boot configuration changes happen only after you review and apply a plan.

## Which files can the wizard write?

Only:

```text
/etc/initramfs-tools/conf.d/resume
/etc/default/grub.d/hibernate-wizard.cfg
```

The wizard must not blindly rewrite `/etc/default/grub`.

## Can rollback overwrite my manual edits?

Rollback is conservative. If a file changed after the wizard wrote it, rollback skips that file and reports the reason.

## Will `apt remove` break hibernation?

No. Removal keeps your working configuration. Purge removes package-owned files but does not delete a user swap file or rewrite working boot configuration.
