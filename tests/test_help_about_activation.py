from pathlib import Path


def test_help_about_sidebar_rows_have_explicit_click_activation() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    assert "Gtk.GestureClick" in source
    assert 'click.connect("released"' in source
    assert 'body.add_controller(click)' in source
    assert 'if key in {"help", "about"}' in source


def test_help_about_pages_still_exist() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    assert '"help": self._help_page' in source
    assert '"about": self._about_page' in source
    assert '"help", "about"' in source
