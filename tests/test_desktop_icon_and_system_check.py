from pathlib import Path


def test_desktop_icon_points_to_bundled_png_asset() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "data" / "icons" / "io.github.ami3go.UbuntuHibernateWizard.png").exists()
    assert (root / "data" / "icons" / "io.github.ami3go.UbuntuHibernateWizard.svg").exists()


def test_system_check_uses_themed_gtk_icon() -> None:
    root = Path(__file__).resolve().parents[1]
    code = (root / "ubuntu_hibernate_wizard" / "ui" / "wizard_window.py").read_text(encoding="utf-8")
    assert "themed:utilities-system-monitor-symbolic" in code
