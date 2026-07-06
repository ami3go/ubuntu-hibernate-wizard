---
title: Use Ubuntu Hibernate Wizard safely
description: Step-by-step workflow for detecting an existing swap target, reviewing planned hibernation changes, applying safely, and verifying after reboot.
---

# Usage

Ubuntu Hibernate Wizard is designed as a review-first workflow. Apply stays blocked when the system does not match the supported v0.42 scope.

## Step-by-step workflow

1. Launch **Ubuntu Hibernate Wizard**.
2. Read the **Introduction** page and confirm the v0.42 scope.
3. Run **System Check**.
4. Select an existing valid swap partition or swap file on **Configuration**.
5. Review exact managed file changes on **Planned Modifications**.
6. Run dry-run first on **Review & Apply**.
7. Apply the plan only after reviewing the log.
8. Reboot manually from the system menu when ready.
9. Run verification after reboot.

## What blocks Apply

Apply remains blocked for:

- zram-only systems;
- no active swap target;
- inactive swap;
- swap smaller than RAM;
- unsupported swap-file filesystem;
- missing GRUB or missing `update-grub`;
- missing initramfs-tools;
- conflicting existing `resume=`, `resume_offset=`, or `RESUME=` configuration;
- random-key or unproven encrypted swap;
- removable-media swap.

## Dry-run mode

Dry-run mode generates a plan and simulates helper events without writing files:

```bash
ubuntu-hibernate-wizard --dry-run
```

From source:

```bash
PYTHONPATH=. python3 -m ubuntu_hibernate_wizard.main --dry-run
```

## Fake-system mode

Fake-system mode is useful for screenshots, tests, and code review:

```bash
PYTHONPATH=. python3 -m ubuntu_hibernate_wizard.main \
  --dry-run \
  --fake-system tests/fixtures/system_profiles/valid_swap_file_ext4.json
```

## Verify after reboot

After manual reboot, run:

```bash
ubuntu-hibernate-wizard --verify
```

The verification command compares active swap, kernel command-line resume parameters, and initramfs resume configuration.
