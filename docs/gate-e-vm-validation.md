# Gate E disposable VM validation

Gate E validates that the real privileged apply path works in a throw-away Ubuntu VM. It is not a normal user workflow and must not be run on a daily-driver system.

Gate E has four automated phases:

1. `--gate-e-preflight` — read-only environment and plan check.
2. `--gate-e-dry-run` — root helper validation with `dry_run=true`, no writes.
3. `--gate-e-validate-plan` — root helper live re-probe and schema validation.
4. `--gate-e-apply` — real managed-file writes and boot-artifact update in the disposable VM only.

The real apply phase requires the exact acknowledgement:

```bash
--gate-e-ack I_UNDERSTAND_THIS_IS_A_DISPOSABLE_VM
```

## Recommended VM workflow

Start from a fresh Ubuntu VM snapshot that uses GRUB and initramfs-tools and already has a valid active swap partition or ext4/btrfs swap file large enough for RAM.

```bash
./tools/gate_e_vm_validate.sh
```

The script runs tests, builds the Debian package, runs preflight, dry-run, and validate-plan. It intentionally skips real apply by default.

To run real apply inside the disposable VM:

```bash
export UHW_GATE_E_REAL_APPLY=1
./tools/gate_e_vm_validate.sh
```

After real apply succeeds:

1. Reboot the VM manually.
2. Run `ubuntu-hibernate-wizard --verify`.
3. Attempt hibernation manually.
4. Resume the VM.
5. Keep the generated JSON report from `dist/gate-e-reports/` with the release notes.

A successful automated apply report has status `manual_hibernate_pending`. Gate E is only considered passed after the manual reboot and hibernate/resume test is recorded.

## Safety rules

- Do not use Gate E real apply on physical hardware unless you are intentionally doing destructive release validation and have full backups.
- Do not use Gate E real apply inside containers; it cannot validate hibernation.
- The helper still writes only:
  - `/etc/initramfs-tools/conf.d/resume`
  - `/etc/default/grub.d/hibernate-wizard.cfg`
- Swap creation/resizing remains out of scope for v0.42.x.
