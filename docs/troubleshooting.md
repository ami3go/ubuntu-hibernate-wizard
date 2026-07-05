# Troubleshooting

Every wizard error carries a stable `error_code`. Find yours below.

## LOCKED
Another wizard instance (or its helper) is running. Close it, or check `/run/ubuntu-hibernate-wizard.lock`.

## NOT_IN_PLAN
Internal safety stop: a mutation was requested that wasn't in the approved plan. Restart the wizard; report if it recurs.

## UNSUPPORTED_FS
The swap file is not on ext4. Btrfs/others are not supported in v1.

## DD_FAILED
Writing the swap file failed — usually disk full mid-write. The wizard cleaned up the partial file; free space and retry.

## NEW_SWAP_INVALID
The freshly created swap file failed activation. Check `dmesg` for filesystem errors.

## SWAPON_FAILED
The replaced swap file could not be activated. The resize journal preserves recovery state — reopen the wizard and follow the recovery prompt.

## UPDATE_GRUB_FAILED / UPDATE_INITRAMFS_FAILED
`update-grub` or `update-initramfs` returned an error; full output is shown in the log expander. Common cause: `/boot` is nearly full — remove old kernels (`sudo apt autoremove`) and use **Repair**.

## Hibernate test failed (no error code)
The system suspended or cold-booted instead of resuming. Check: Secure Boot enabled (kernel lockdown), swap smaller than used RAM, or graphics driver resume issues. Collect logs: `journalctl -b -1 | grep -iE "hibern|resume|pm:"`.

## Verification shows offset mismatch
Expected after any swap resize outside the wizard. Press **Repair and Reboot** — it recalculates the offset and rewrites GRUB + initramfs.
