# Installation

## From a release .deb
```bash
sudo apt install ./ubuntu-hibernate-wizard_*.deb
```
Installs the app, a polkit policy for the privileged helper, and (inert until you enable it) the boot-time guard service.

## Dependencies
python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, pkexec, polkitd, initramfs-tools, grub-common, util-linux, e2fsprogs.

## Uninstall
```bash
sudo apt remove ubuntu-hibernate-wizard    # keeps your working hibernation setup
sudo apt purge  ubuntu-hibernate-wizard    # also removes wizard-written config
```
Purge never deletes your swap file or edits GRUB — use the in-app "Remove hibernation" flow first if you want a full reversal.
