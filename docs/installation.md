---
title: Install Ubuntu Hibernate Wizard
description: Install the Ubuntu Hibernate Wizard .deb package, review GTK4/libadwaita dependencies, and understand safe package removal.
---

# Installation

Installing Ubuntu Hibernate Wizard does **not** enable hibernation by itself. The package only installs the application, desktop launcher, helper, policy file, and documentation. Boot configuration changes happen only after a reviewed Apply action.

## Install from a release `.deb`

Download the `.deb` from the latest GitHub release, then run:

```bash
sudo apt install ./ubuntu-hibernate-wizard_*.deb
```

The package installs:

- the GTK4/libadwaita desktop wizard;
- a desktop launcher;
- a polkit policy for the privileged helper;
- documentation and Gate E/F validation tools;
- inert guard service files for optional future drift checks.

## Runtime dependencies

```text
python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1,
pkexec, polkitd, initramfs-tools, grub-common, util-linux, e2fsprogs
```

Recommended packages:

```text
mokutil, gnome-shell
```

`btrfs-progs` is needed only when the selected swap target is a btrfs swap file.

## Build from source

```bash
git clone https://github.com/ami3go/ubuntu-hibernate-wizard.git
cd ubuntu-hibernate-wizard
python3 -m pytest -q
make deb
sudo apt install ./dist/ubuntu-hibernate-wizard_*.deb
```

## Run without installing

Use dry-run mode when developing or reviewing the GUI:

```bash
PYTHONPATH=. python3 -m ubuntu_hibernate_wizard.main --dry-run
```

Use a fake system fixture to avoid probing the host:

```bash
PYTHONPATH=. python3 -m ubuntu_hibernate_wizard.main \
  --dry-run \
  --fake-system tests/fixtures/system_profiles/valid_swap_file_ext4.json
```

## Uninstall

```bash
sudo apt remove ubuntu-hibernate-wizard
sudo apt purge ubuntu-hibernate-wizard
```

`apt remove` keeps a working hibernation configuration.

`apt purge` removes package-owned state and helper files, but remains conservative: it does not delete a user swap file and does not rewrite a working GRUB configuration. Use the wizard rollback/recovery flow when you want a controlled reversal of wizard-managed files.
