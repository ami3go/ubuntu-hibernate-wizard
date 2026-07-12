# Ubuntu Hibernate Wizard 0.4.3 RC5

Release candidate update after real-system testing on a machine with RAM larger than the existing swap file.

## Versioning

- User-visible app version: `0.4.3-rc5`
- Python package version: `0.4.3rc5`
- Debian package version: `0.4.3~rc5-1`

## Changes since RC4

- System Check no longer blocks **Continue to Configuration** only because no existing active disk swap target is currently usable for hibernation.
- This specifically fixes systems where the current swap file is smaller than RAM.
- The condition remains a warning: Configuration is available so the user can select managed `/swap.img` create/resize.
- Real fatal blockers still block Configuration, such as unsupported boot stack, missing kernel hibernate support, or read-only configuration paths.

## Validation

Automated test suite must pass before publishing this release candidate. GTK smoke may be skipped in the sandbox when GTK/gi runtime is unavailable.
