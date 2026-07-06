# 0.42.12

- Moved the Recommended swap-file size slider mark above the slider to avoid overlap with the Minimum mark.
- Kept Minimum and 2× RAM marks below the slider while preserving the manual input and preset buttons.

# 0.42.8

- Added production/public-use hardening: fake-system golden fixtures, encrypted swap blocking, Diagnostic ZIP export, GTK CI smoke tests, static safety tests, stable GUI object names, and complete runtime diagram documentation.

# Changelog

## 0.42.6 - Documentation and GitHub Pages refresh

- Reworked the GitHub README as a complete project landing page with screenshot overview, safety model, supported-system matrix, installation, development, and documentation links.
- Added GTK4 menu screenshots to GitHub Pages assets and linked them from screenshots/examples documentation.
- Expanded GitHub Pages content for Installation, Usage, Troubleshooting, FAQ, Architecture, Testing, Rollback, and deployment/SEO notes.
- Updated MkDocs Material configuration with navigation features, code-copy support, repository links, and a more accurate search-oriented site description.
- Kept runtime scope unchanged: existing active swap partition/file targets only.

## 0.42.5 - Code cleanup and helper hardening

- Removed stale duplicate helper source files and unused helper methods left from older swap-creation flows.
- Reworked CLI verification to use the v0.42 system probe and swap classifier instead of duplicate filefrag parsing.
- Made generated GRUB fragments idempotent so matching resume kernel parameters are not duplicated.
- Strengthened one-shot helper schema validation for app version, dry-run type, duplicate steps/files, rollback mode, UUID, and selected-target fields.
- Removed unused Gate E host helper and refreshed tests for cleanup/hardening behavior.

## 0.42.4 - Gate F release-candidate evidence tooling

- Added Gate F CLI workflow to validate Gate E apply evidence plus a manual hibernate/resume record.
- Added manual record generation with exact Gate E report SHA-256 linking.
- Added release-candidate manifest generation and documentation.
- Updated Help/Finish gate messaging to describe Gate F evidence requirements.

## 0.42.2 - Gate E validation harness

- Added disposable-VM Gate E validation CLI modes.
- Added guarded real-apply Gate E command requiring exact VM acknowledgement.
- Added JSON Gate E reports with redacted summaries.
- Added `tools/gate_e_vm_validate.sh` release-validation helper.
- Added Gate E documentation and safety tests.


## 0.42.1 - GTK4 hardening update

- System Check now uses an unprivileged read-only probe and avoids pkexec prompts.
- UI now loads bundled original SVG icons instead of theme symbolic icon names.
- Added GTK-style apply and runtime hibernation process diagrams.
- Added GUI diagnostic report export with redaction.
- Strengthened helper one-shot schema validation and live reclassification before apply.
- Blocked btrfs swap-file targets unless btrfs map-swapfile returns the kernel resume_offset.
- Blocked encrypted swap unless stable initramfs mapping is explicitly proven.
- Added hardening tests and golden config tests.

## [0.42.0] - 2026-07-06

### Changed

- Reworked the app around the v0.42 GTK4/libadwaita implementation task.
- Added persistent sidebar navigation: Introduction, System Check, Configuration, Planned Modifications, Review & Apply, Finish, Help, and About.
- Added service-layer swap target classification for existing active swap partitions/files.
- Added dry-run and fake-system modes for safe UI/planner testing.
- Updated the privileged helper with the v0.42 one-shot `apply-plan` JSON protocol.
- Moved apply scope to managed files only: `/etc/initramfs-tools/conf.d/resume` and `/etc/default/grub.d/hibernate-wizard.cfg`.
- Added original GTK-style icon assets to the package tree.

### Safety

- Removed swap creation/resizing from the v0.42 apply path.
- Removed fstab, systemd sleep, and runtime polkit rule changes from the v0.42 apply path.
- Blocked zram, undersized swap, unsupported filesystems, inactive swap, and non-GRUB/initramfs-tools systems.
- Added tests for swap decision logic, generated config, conflict detection, and btrfs offset parsing.

## [0.36.8] - 2026-07-06

- Previous GTK4 wizard and documentation/SEO review baseline.
