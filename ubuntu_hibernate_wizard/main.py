"""Entry point. CLI flags (SS27.7) are handled read-only in-process;
otherwise launches the GTK4 wizard (helper session = one pkexec, SS26.1)."""
import sys


def main() -> int:
    from ubuntu_hibernate_wizard import cli
    code = cli.main(sys.argv[1:])
    if code is not None:
        return code
    from ubuntu_hibernate_wizard.ui.wizard_window import WizardApp
    from ubuntu_hibernate_wizard.backend.session import HelperSession
    return WizardApp(HelperSession()).run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
