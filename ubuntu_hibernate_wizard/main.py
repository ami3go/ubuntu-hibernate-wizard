"""Entry point for CLI flags and GTK4 wizard."""
from __future__ import annotations

import sys


def _extract_gui_options(argv: list[str]) -> tuple[list[str], bool, str | None]:
    rest: list[str] = []
    dry_run = False
    fake_system = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--fake-system":
            try:
                fake_system = argv[i + 1]
            except IndexError:
                raise SystemExit("--fake-system requires a fixture path")
            i += 1
        else:
            rest.append(arg)
        i += 1
    return rest, dry_run, fake_system


def main() -> int:
    from ubuntu_hibernate_wizard import cli
    argv, dry_run, fake_system = _extract_gui_options(sys.argv[1:])
    code = cli.main(argv)
    if code is not None:
        return code
    from ubuntu_hibernate_wizard.ui.wizard_window import WizardApp
    from ubuntu_hibernate_wizard.backend.session import HelperSession
    return WizardApp(HelperSession(dry_run=dry_run, fake_system=fake_system)).run([sys.argv[0], *argv])


if __name__ == "__main__":
    raise SystemExit(main())
