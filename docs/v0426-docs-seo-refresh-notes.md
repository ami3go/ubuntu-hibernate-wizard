# v0.42.6 Documentation and GitHub Pages Refresh Notes

This update refreshes the GitHub README and MkDocs GitHub Pages content without changing the v0.42 runtime scope.

## Updated

- Rewrote the GitHub README as a project landing page with banner, screenshot overview, support matrix, safety model, installation, safe source run commands, and documentation links.
- Added generated GTK4 menu screenshots to `docs/assets/screenshots/menu/` and linked them from the README and GitHub Pages.
- Reworked the GitHub Pages home page for clearer search intent around Ubuntu hibernation, swap files, resume UUID, resume_offset, GRUB, and initramfs-tools.
- Expanded Installation, Usage, Screenshots, Troubleshooting, FAQ, Architecture, Testing, Rollback, and GitHub Pages deployment pages.
- Updated MkDocs Material configuration with navigation features, code-copy support, repository links, and a more accurate site description.
- Added front matter descriptions for search snippets.

## Scope unchanged

v0.42.6 still supports existing active swap partition/file targets only. It does not create swap, resize swap, enable inactive swap, edit `/etc/fstab`, change Secure Boot settings, or reboot automatically.

## Release boundary unchanged

Gate D remains passed. Gate E/F tooling is implemented, but real disposable-VM hibernate/resume validation is still pending.
