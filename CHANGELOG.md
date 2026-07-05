# Changelog

## [0.3.2] - 2026-07-05
- Fix overlapping Minimum/Recommended slider labels: Recommended now sits
  above the track; wider GNOME-Disks-style slider with 4 GB ticks


## [0.3.1] - 2026-07-05
- Swap size slider with RAM-mapped marks (Minimum / Recommended / Double RAM),
  synced with preset rows; detected RAM shown in the header


## [0.3.0] - 2026-07-05
- Back/Next buttons on every page - no more dead ends
- Full wizard flow: Swap size -> Plan -> Apply (live progress) -> Verify -> Repair
- "Verify existing configuration" shortcut on Welcome for the post-reboot flow


## [0.2.1] - 2026-07-05
- Fix: package was uninstallable on modern Ubuntu — depend on pkexec + polkitd
  instead of the removed transitional policykit-1


## [0.2.0] - 2026-07-05
- CLI verify mode (`--verify --json`, exit codes 0/2/3)
- Boot-time guard service + session notify watcher (shipped inert)
- State schema v1 with swap_preexisting provenance
- Original banner and GNOME-style scalable icon

## [0.1.0] - 2026-07-05
- Initial release: parsers, GRUB/fstab editors, verification (§22 fixture),
  crash-safe resize with journal, single-elevation helper session, GTK4 UI
  (Welcome + System Check), .deb packaging
