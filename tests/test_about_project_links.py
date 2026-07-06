from pathlib import Path


def test_about_page_contains_project_links() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    assert "Project links" in source
    assert "https://ami3go.github.io/ubuntu-hibernate-wizard/" in source
    assert "https://github.com/ami3go/ubuntu-hibernate-wizard" in source
    assert "Gtk.LinkButton.new_with_label" in source
