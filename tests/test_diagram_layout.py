from pathlib import Path


def test_process_diagram_uses_overlay_badge_layout() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    assert "Gtk.Overlay" in source
    assert "uhw-diagram-badge" in source
    assert "step_box.set_size_request(124, -1)" in source
    assert 'icon_size = 62 if icon == "app-icon" else 56' in source


def test_process_diagram_css_uses_smaller_cards_and_badge_style() -> None:
    css = Path("ubuntu_hibernate_wizard/css/app.css").read_text(encoding="utf-8")
    assert ".uhw-diagram-badge" in css
    assert "min-width: 112px" in css
    assert "padding: 10px" in css
