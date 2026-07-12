from pathlib import Path

from ubuntu_hibernate_wizard.backend.session import HelperSession


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "fake_systems"


def test_small_existing_swap_does_not_block_configuration() -> None:
    session = HelperSession(fake_system=str(FIXTURE_ROOT / "swapfile_too_small"))
    info = session.detect()
    assert info.hard_stop
    assert info.recommended_target is None
    assert info.can_continue_to_configuration
    assert info.configuration_blocking_reasons == []


def test_no_existing_swap_does_not_block_configuration() -> None:
    session = HelperSession(fake_system=str(FIXTURE_ROOT / "no_swap"))
    info = session.detect()
    assert info.hard_stop
    assert info.recommended_target is None
    assert info.can_continue_to_configuration
    assert info.configuration_blocking_reasons == []


def test_read_only_config_still_blocks_configuration() -> None:
    session = HelperSession(fake_system=str(FIXTURE_ROOT / "read_only_filesystem"))
    info = session.detect()
    assert not info.can_continue_to_configuration
    assert any("read-only" in reason.lower() for reason in info.configuration_blocking_reasons)


def test_ui_uses_configuration_specific_gate_for_continue_button() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    assert "can_continue_to_configuration" in source
    assert "next_btn.set_sensitive(self.detect_info is not None and self.detect_info.can_continue_to_configuration)" in source
    assert "self._check_next_btn.set_sensitive(self.detect_info.can_continue_to_configuration)" in source
