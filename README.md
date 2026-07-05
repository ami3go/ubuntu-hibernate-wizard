<p align="center">
  <img src="data/banner.svg" alt="Ubuntu Hibernate Wizard - enable hibernation on Ubuntu with swap file, GRUB resume and GNOME power menu support" width="100%">
</p>

# Ubuntu Hibernate Wizard – Enable Hibernation on Ubuntu with Swap File, GRUB Resume & GNOME Hibernate Button

**Ubuntu Hibernate Wizard** is a safe GTK4/libadwaita desktop app for people who want to **enable hibernation on Ubuntu** without manually editing GRUB, initramfs, swap-file settings, or GNOME power-menu extensions.

It helps with common Ubuntu hibernation problems such as:

- **Ubuntu hibernate not working** after creating or resizing a swap file
- `systemctl hibernate` shuts down but does not resume the session
- missing or stale `resume=UUID=...` and `resume_offset=...` kernel parameters
- GRUB/initramfs configuration mistakes
- no Hibernate button in the GNOME power menu
- uncertainty about swap-file size, swap offset, and post-reboot verification

The wizard checks your system, creates or resizes the swap file, configures resume parameters, updates initramfs, verifies hibernation support, saves a detailed log, and links to GNOME extensions that add Hibernate actions to the desktop power menu.

## Quick install on Ubuntu

Download the `.deb` package from the latest GitHub release, then install it with:

```bash
sudo apt install ./ubuntu-hibernate-wizard_*.deb
```

Launch **Hibernate Wizard** from the Ubuntu app grid.

You can also run verification from the terminal:

```bash
ubuntu-hibernate-wizard --verify --json
```

## What problem does this app solve?

Ubuntu can hibernate, but enabling it with a swap **file** is easy to break. The kernel needs two correct values at boot:

```text
resume=UUID=d76e67b3-... resume_offset=5986304
```

If the UUID or physical swap-file offset is wrong, Ubuntu may appear to hibernate but then cold-boot instead of restoring your session. This often happens after a swap file is recreated, resized, moved by the filesystem, or after boot configuration changes.

Ubuntu Hibernate Wizard automates the full workflow:

1. detects the current Ubuntu, filesystem, swap, GRUB, initramfs, and Secure Boot state;
2. creates or resizes the swap file, including a custom swap size field;
3. calculates the correct filesystem UUID and swap-file physical offset;
4. writes a reviewed plan before any privileged change is made;
5. updates `/etc/fstab`, GRUB resume parameters, systemd sleep configuration, and polkit rules when needed;
6. rebuilds initramfs;
7. saves a timestamped log to `~/Downloads/hibernation_wizard_<timestamp>.log`;
8. offers **Reboot Now** and **Reboot Later** actions;
9. guides you to GNOME extensions for adding Hibernate to the power menu.

## Main features

- **Guided Ubuntu hibernation setup** — step-by-step wizard for swap file, GRUB, initramfs, systemd, and GNOME follow-up
- **Custom swap size** — choose a preset or enter your own swap-file size in GB
- **Safe swap-file creation and resize** — build-aside approach with backups and recovery journal
- **Fix stale `resume_offset`** — recalculates the swap-file offset instead of reusing old values
- **Verbose live apply log** — collapsible Step 5 log with timestamps, commands, file paths, backup paths, kernel parameters, and exact changes
- **Saved log file** — writes the full log to your Downloads folder for debugging or bug reports
- **One password prompt per run** — uses one pkexec-elevated helper session, not repeated sudo prompts
- **Post-reboot verification** — checks if hibernation configuration still matches the current swap file
- **One-click repair flow** — detects UUID/offset drift and suggests repair
- **Full rollback model** — every modified file is backed up before mutation
- **GNOME Hibernate button guidance** — links to Hibernate Status Button and System Action - Hibernate extensions
- **CLI verification mode** — useful for scripts, monitoring, or support diagnostics

## Who is it for?

This app is useful if you searched for:

- “enable hibernation Ubuntu”
- “Ubuntu hibernate not working”
- “Ubuntu 24.04 hibernate swap file”
- “Ubuntu resume_offset swap file”
- “systemctl hibernate does not resume”
- “add Hibernate button GNOME power menu”
- “GRUB resume UUID resume_offset Ubuntu”
- “Ubuntu laptop hibernate instead of suspend”

It is designed for Ubuntu desktop users who want a safer alternative to copying terminal commands from random forum posts.

## Supported systems

| Requirement | Supported now |
|---|---|
| Ubuntu release | Ubuntu 24.04 LTS, Ubuntu 26.04 LTS; interim releases show a warning |
| Desktop | GNOME with GTK4/libadwaita |
| Bootloader | GRUB |
| Initramfs | initramfs-tools |
| Swap type | swap **file** |
| Root filesystem | ext4 |
| Secure Boot | detected; advanced confirmation required |

Planned or experimental areas are tracked in the documentation and issue tracker. Btrfs, LUKS-encrypted swap, swap partitions, and systemd-boot need different handling and are not the default supported path yet.

## Screenshots / GitHub Pages documentation

Project documentation is published with GitHub Pages:

```text
https://ami3go.github.io/ubuntu-hibernate-wizard/
```

Useful documentation pages:

- [Installation guide](docs/installation.md)
- [Usage guide](docs/usage.md)
- [How Ubuntu hibernation works](docs/how-hibernation-works.md)
- [Troubleshooting Ubuntu hibernation](docs/troubleshooting.md)
- [Rollback and recovery](docs/rollback-and-recovery.md)
- [Architecture and safety model](docs/architecture.md)
- [FAQ](docs/faq.md)

## GNOME extensions for Hibernate button

Ubuntu Hibernate Wizard configures the operating system side of hibernation. For a convenient desktop menu entry, the final page links to these GNOME Shell extensions:

- [Hibernate Status Button](https://extensions.gnome.org/extension/755/hibernate-status-button/) — adds Hibernate and Hybrid Sleep actions to the GNOME status menu
- [System Action - Hibernate](https://extensions.gnome.org/extension/3814/system-action-hibernate/) — adds Hibernate as a GNOME system action

## Build from source

```bash
make test   # run unit tests without root and without system changes
make deb    # build the .deb package into dist/
```

Runtime dependencies:

```text
python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, pkexec, polkitd
```

## Safety model

The GUI never runs privileged shell commands directly. A separate root helper is launched once per run via `pkexec`. The helper accepts only a fixed set of validated operations and refuses mutations that are not part of the reviewed plan shown in the wizard.

Before changing the system, the app records what will be changed and where backups will be stored. Every changed file is backed up first. Package installation itself does not enable hibernation or modify boot configuration; changes happen only after the user reviews and applies the plan.

## FAQ: Ubuntu hibernation search questions

### How do I enable hibernation on Ubuntu with a swap file?

Use the wizard to check compatibility, choose or create a swap file, calculate the correct `resume=UUID=...` and `resume_offset=...`, update GRUB/initramfs, reboot, and run verification. The app is designed to avoid the common mistake of using an outdated swap-file offset.

### Why does Ubuntu hibernate but not resume?

The most common reason is that the kernel boot parameters no longer match the real swap file. A stale UUID or stale `resume_offset` can make Ubuntu boot normally instead of restoring the hibernated image. The wizard recalculates and verifies both values.

### Why is `resume_offset` important for Ubuntu swap-file hibernation?

For swap-file hibernation, the kernel must know the physical disk offset of the swap file. This is different from swap partitions, where the block device itself is used. If the file is recreated or moved, the offset can change.

### Does this add a Hibernate button to the GNOME power menu?

The app links to GNOME extensions that can add Hibernate actions to the power menu. The wizard focuses on safe system configuration and verification; the extensions provide the convenient desktop button.

### Does this change my system during installation?

No. Installing the `.deb` only installs the app. The wizard changes hibernation configuration only after you review the plan and explicitly apply it.

## Project keywords

Ubuntu hibernate, Ubuntu hibernation, enable hibernation Ubuntu, Ubuntu hibernate not working, Ubuntu swap file hibernate, resume_offset, resume UUID, GRUB hibernate, initramfs hibernate, systemctl hibernate, GNOME Hibernate button, Hibernate Status Button, System Action Hibernate, Linux laptop hibernation.

## Contributing

Bug reports, Ubuntu compatibility reports, translation help, screenshots, documentation improvements, and support for more filesystems or bootloaders are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

GPL-3.0-or-later. Artwork, including banner and icon, is original and licensed CC-BY-4.0.
