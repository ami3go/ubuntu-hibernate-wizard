---
title: Testing and release gates
description: Run Ubuntu Hibernate Wizard unit tests, dry-run GUI tests, fake-system tests, Gate E disposable VM validation, and Gate F release-candidate evidence checks.
---

# Testing

## Unit tests

Run tests without root:

```bash
PYTHONPATH=. pytest -q
```

or:

```bash
make test
```

## GUI safe mode

Run the GUI in dry-run mode:

```bash
PYTHONPATH=. python3 -m ubuntu_hibernate_wizard.main --dry-run
```

Use a fixture without probing or modifying the real host:

```bash
PYTHONPATH=. python3 -m ubuntu_hibernate_wizard.main \
  --dry-run \
  --fake-system tests/fixtures/fake_systems/swapfile_ok
```


## Production-readiness test groups

v0.42.8 includes these release-blocking test groups:

```bash
PYTHONPATH=. pytest tests/integration -q   # fake-system golden fixtures
PYTHONPATH=. pytest tests/static -q        # protected-file and command-bypass checks
PYTHONPATH=. pytest tests/gui -q           # GTK smoke tests when python3-gi is installed
```

GTK smoke tests are intended to run in Ubuntu CI with system Python, `python3-gi`, GTK4, libadwaita, Xvfb, and dbus-run-session.

The fake-system fixture root is:

```text
tests/fixtures/fake_systems/
```

Each fixture includes command/file snapshots and golden expected outputs for swap targets, blockers, warnings, plan, and diagnostic summary.

## Gate E disposable VM validation

Real Apply must be tested only in a disposable Ubuntu VM after dry-run and golden configuration tests pass.

See [Gate E disposable VM validation](gate-e-vm-validation.md).

## Gate F release-candidate evidence

After Gate E real apply and manual hibernate/resume are completed in a disposable VM, run the Gate F evidence checker.

See [Gate F release-candidate evidence check](gate-f-release-candidate.md).

## Documentation checks

When MkDocs is installed, build the GitHub Pages site strictly:

```bash
mkdocs build --strict
```
