# Ubuntu Hibernate Wizard 0.4.3 RC3

Release candidate update after RC2 real-system UI review.

## Versioning

- User-visible app version: `0.4.3-rc3`
- Python package version: `0.4.3rc3`
- Debian package version: `0.4.3~rc3-1`

## Changes since RC2

- Planned Modifications keeps the compact visible Planned changes table.
- Technical details now includes richer information about changes:
  - generated resume/GRUB preview when available
  - helper step IDs
  - change type
  - technical impact per step
  - affected file purpose
  - rollback scope and backup manifest location

## Validation

Automated test suite must pass before publishing this release candidate. GTK smoke may be skipped in the sandbox when GTK/gi runtime is unavailable.
