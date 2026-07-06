from pathlib import Path


def test_finish_page_restores_post_restart_verification_section() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    finish_section = source.split("def _finish_page", 1)[1].split("def _help_page", 1)[0]
    assert "Verification after restart" in finish_section
    assert "Run verification after restart" in finish_section
    assert "btn_verify" in finish_section
    assert "self._start_post_restart_verify" in finish_section
    assert "resume UUID" in finish_section
    assert "resume offset" in finish_section


def test_post_restart_verification_methods_exist() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    assert "def _start_post_restart_verify" in source
    assert "def _post_restart_verify_worker" in source
    assert "def _post_restart_verify_done" in source
    assert "Verification passed" in source
    assert "Verification blocked" in source
