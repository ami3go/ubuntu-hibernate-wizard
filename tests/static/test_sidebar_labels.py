from __future__ import annotations

from pathlib import Path


def test_review_apply_sidebar_label_is_explicit_and_named():
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text()
    assert '"apply": "Review & Apply"' in source
    assert 'Gtk.Label(label=title' in source
    assert 'nav_label_{key}' in source
    assert 'nav_apply' in source or 'nav_{key}' in source
