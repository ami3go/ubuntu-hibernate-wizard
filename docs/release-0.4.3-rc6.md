# Ubuntu Hibernate Wizard 0.4.3 RC6

Release candidate update after a real-system failure caused by insufficient free space for managed swap-file resize.

## Versioning

- User-visible app version: `0.4.3-rc6`
- Python package version: `0.4.3rc6`
- Debian package version: `0.4.3~rc6-1`

## Changes since RC5

- Added free-space detection for the filesystem that contains `/swap.img`.
- Configuration now shows a free-space marker for managed swap-file create/resize.
- Configuration blocks continuing when the requested managed swap file cannot fit.
- Planner blocks impossible swap-file requests before Review & Apply.
- Privileged helper performs a final free-space preflight before `/etc/fstab` edits, `swapoff`, old swap-file rename, new allocation, or boot configuration writes.
- The free-space calculation is conservative: when resizing, the old swap file is kept for rollback, so the system must have enough current free space for the full new requested swap file plus a 1 GiB safety reserve.

## Validation

Automated test suite must pass before publishing this release candidate. GTK smoke may be skipped in the sandbox when GTK/gi runtime is unavailable.
