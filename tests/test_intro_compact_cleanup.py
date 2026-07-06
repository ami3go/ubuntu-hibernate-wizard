from pathlib import Path


def test_intro_removes_large_before_continue_and_runtime_cards() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    intro = source.split("def _intro_page", 1)[1].split("def _check_page", 1)[0]
    assert "Before you continue" not in intro
    assert "Runtime hibernation / resume diagram" not in intro
    assert "runtime_diagram" not in intro
    assert "Continue to System Check" in intro
