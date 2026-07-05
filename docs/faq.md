# FAQ

**Secure Boot?** Kernel lockdown usually blocks hibernation. The wizard warns and requires advanced-mode confirmation; disabling Secure Boot in firmware is the reliable path today.

**Encrypted disk (LUKS)?** Not supported in v1 — it's the top roadmap item, since encrypted installs are the Ubuntu default.

**Virtual machines?** Usually unsupported by the hypervisor; the wizard warns.

**zram?** Kept for runtime swapping; hibernation needs a disk swap file, which the wizard adds alongside.

**Will `apt remove` break my hibernation?** No — removal keeps your working configuration. Use the in-app "Remove hibernation" for a full reversal.
