from pathlib import Path


def test_configuration_page_reports_and_gates_free_space() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    assert "swapfile_free_space_problem" in source
    assert "swapfile_free_space_summary" in source
    assert "Not enough space for selected managed /swap.img size" in source
    assert "Free up disk space" in source
    assert "return self._swapfile_free_space_problem() is None" in source


def test_privileged_helper_preflights_free_space_before_swapoff_or_fstab() -> None:
    source = Path("ubuntu_hibernate_wizard/backend/privileged_helper.py").read_text(encoding="utf-8")
    assert "def _preflight_swapfile_free_space" in source
    assert "INSUFFICIENT_FREE_SPACE_FOR_SWAPFILE" in source
    ensure = source.split("def _ensure_managed_swap_file", 1)[1].split("def _select_live_swapfile_target", 1)[0]
    assert ensure.index("_preflight_swapfile_free_space") < ensure.index("_ensure_fstab_entry")
    assert ensure.index("_preflight_swapfile_free_space") < ensure.index('["swapoff", path]')
