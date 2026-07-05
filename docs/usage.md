# Usage Guide

## Before you start

- Save your work — a reboot is required, and the final step tests hibernation.
- Have ~1.2× your RAM in free disk space (an 18 GB swap file for 16 GB RAM).
- On laptops: plug in the charger.

## Step-by-step

### 1. Welcome
Read what will be changed (GRUB, fstab, initramfs, systemd sleep, polkit). Tick the consent checkbox to continue. Nothing is modified yet.

### 2. System check
The wizard verifies: Ubuntu version, ext4 root, GRUB, initramfs-tools, kernel hibernate support, Secure Boot state, and existing swap.

- ✅ All green — continue.
- ⚠️ **Secure Boot enabled** — kernel lockdown usually blocks hibernation. You may continue in advanced mode, but the hibernate test may fail; disabling Secure Boot in firmware settings is the reliable fix.
- 🛑 Unsupported (Btrfs, no GRUB, VM without support) — the wizard stops safely and explains why.

### 3. Swap file
Pick a size: **Recommended (RAM + 2 GB)** suits almost everyone. If you have zram only, a disk swap file is created alongside it; zram is kept.

### 4. Review the plan
Every command the wizard intends to run is listed. Nothing executes until you press **Apply Changes**. You'll be asked for your password **once** here.

### 5. Apply
Watch live progress: swap creation (the longest step — writing 18 GB takes a few minutes), fstab, UUID and offset calculation, GRUB, initramfs, polkit. Every original file is backed up to `/var/backups/ubuntu-hibernate-wizard/<timestamp>/` first. If anything fails, the wizard stops and offers **Roll Back**.

### 6. Reboot
Required — the kernel must load the new resume parameters.

### 7. Verify (after reboot)
Open the wizard again. It compares what the kernel is actually using against reality:

| Check | Meaning |
|---|---|
| Active swap | your swap file is live |
| Resume UUID | kernel points at the right filesystem |
| Resume offset | kernel points at the right position in the file |
| initramfs | early-boot config matches |

A ❌ on offset is the classic stale-offset bug — press **Repair and Reboot** and the wizard recalculates and rewrites everything.

### 8. Test hibernate
Press **Test Hibernation**. The machine writes a marker, hibernates (screen off, power off), and when you power it back on your session should resume exactly where it was. The wizard confirms the test on resume.

### 9. Optional extras
- Add a **Hibernate button** to the GNOME power menu (extension).
- Enable the **boot-time guard** so you're notified if a kernel update ever breaks the configuration.

## Command line (v1.2+)

```bash
sudo ubuntu-hibernate-wizard --verify --json
```

Exit codes: `0` ok · `2` mismatch found · `3` cannot check (run with sudo).

## Removing hibernation

Menu → **Remove hibernation**: reverses all configuration and can optionally delete the swap file (only if the wizard created it), reclaiming the disk space.
