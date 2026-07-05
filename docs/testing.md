# Testing

```bash
make test          # or: python3 -m pytest tests/ -v
```
41 tests, all fixture-based — no root, no system changes, safe anywhere. Coverage maps to spec §12: parser edge cases, GRUB/fstab editing idempotency, the §22 stale-offset acceptance fixture, resize-journal recovery table, guard notification logic, provenance rules, CLI exit codes. Add new command-output samples under `tests/` as string fixtures.
