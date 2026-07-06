from pathlib import Path


def test_apply_does_not_auto_navigate_to_finish() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    apply_done = source.split("def _apply_done", 1)[1].split("def _finish_page", 1)[0]
    assert 'self._show_page("finish")' not in apply_done
    assert "Review the live log above" in apply_done
    assert "btn_continue_finish" in source


def test_finish_page_has_no_release_gate_card() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    finish_section = source.split("def _finish_page", 1)[1].split("def _help_page", 1)[0]
    assert "Current release gate" not in finish_section
    assert "Gate F evidence tooling" not in finish_section
