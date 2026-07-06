from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("gi")
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ubuntu_hibernate_wizard.backend.session import HelperSession  # noqa: E402
from ubuntu_hibernate_wizard.ui.wizard_window import WizardApp, WizardWindow  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_systems" / "swapfile_ok"
REQUIRED_NAMES = {
    "app_window",
    "page_discovery",
    "page_swap_target",
    "page_plan",
    "page_apply",
    "nav_apply",
    "nav_label_apply",
    "page_verify",
    "page_diagnostics",
    "runtime_diagram",
    "btn_analyze",
    "btn_apply",
    "btn_export_diagnostics",
    "btn_rollback",
    "btn_verify",
    "status_banner",
    "plan_summary",
    "blocker_list",
    "warning_list",
}


def _walk(widget):
    yield widget
    child = widget.get_first_child() if hasattr(widget, "get_first_child") else None
    while child:
        yield from _walk(child)
        child = child.get_next_sibling()


def test_gtk_and_adwaita_imports():
    assert Gtk.MAJOR_VERSION >= 4
    assert Adw is not None


def test_main_window_constructs_without_root():
    app = WizardApp(HelperSession(dry_run=True, fake_system=str(FIXTURE)))
    win = WizardWindow(app, app.controller)
    assert win.get_name() == "app_window"


def test_critical_widget_object_names_exist():
    app = WizardApp(HelperSession(dry_run=True, fake_system=str(FIXTURE)))
    win = WizardWindow(app, app.controller)
    for page in ["intro", "check", "config", "plan", "apply", "finish", "help"]:
        win._show_page(page)
    names = {w.get_name() for w in _walk(win) if hasattr(w, "get_name")}
    missing = REQUIRED_NAMES - names
    assert missing == set()


def test_diagnostic_export_action_reachable(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    session = HelperSession(dry_run=True, fake_system=str(FIXTURE))
    app = WizardApp(session)
    win = WizardWindow(app, app.controller)
    win._show_page("check")
    session.detect()
    path = session.export_diagnostics()
    assert path.endswith(".zip")
