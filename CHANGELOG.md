# Changelog

## Unreleased
- Documentation: SEO-optimized README and GitHub Pages home page for Ubuntu hibernation search terms.

## [0.3.5] - 2026-07-05
- Add **System Action - Hibernate** as a second GNOME Shell extension option on the final Next Steps page.
- Make Step 5 apply logs more verbose: record exact files, commands, backup paths, selected swap size, UUID, resume offset, policy changes, and changed/already-correct results.
- Implement and log the fstab, systemd sleep drop-in, and polkit rule helper steps that were already listed in the plan.

## [0.3.4] - 2026-07-05
- Add custom swap-size text field on the swap step.
- Replace the single-line apply status with a collapsible timestamped live log.
- Save the full apply log to `~/Downloads/hibernation_wizard_<timestamp>.log` when the apply step finishes.
- Add **Reboot Now** and **Reboot Later** choices after successful apply.
- Add a final next-steps page linking to the GNOME Hibernate Status Button extension.

## [0.3.3] - 2026-07-05
- Add GitHub Pages publishing workflow using current Pages actions.
- Add MkDocs site metadata and GitHub Pages deployment documentation.

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
