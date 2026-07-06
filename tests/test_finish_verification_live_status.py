from pathlib import Path


def test_finish_verification_has_live_status_window() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    finish_section = source.split("def _finish_page", 1)[1].split("def _help_page", 1)[0]
    assert "verification_live_log" in finish_section
    assert "verification_live_status_window" in finish_section
    assert "Gtk.TextView" in finish_section
    assert "Press Run verification after restart to see live read-only checks here" in finish_section


def test_post_restart_verification_writes_live_status_messages() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    verify_section = source.split("def _clear_finish_verify_log", 1)[1].split("def _apply_done", 1)[0]
    assert "def _append_finish_verify_log" in verify_section
    assert "Starting post-restart verification." in verify_section
    assert "Mode: read-only" in verify_section
    assert "Detailed check results:" in verify_section
    assert "active swap target, resume UUID, resume offset, GRUB and initramfs" in verify_section
