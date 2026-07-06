from __future__ import annotations

import pytest

from ubuntu_hibernate_wizard.backend import privileged_helper as helper
from ubuntu_hibernate_wizard.constants import APP_VERSION, GRUB_FRAGMENT, PROTOCOL_VERSION, RESUME_FILE
from ubuntu_hibernate_wizard.services.hibernate_planner import (
    FSTAB_FILE,
    SwapFileRequest,
    build_swapfile_modification_plan,
    suggested_swap_sizes,
    swapfile_slider_marks,
)
from ubuntu_hibernate_wizard.services.swap_target_model import SystemProfile


def _profile_without_swap() -> SystemProfile:
    return SystemProfile(
        ram_bytes=8 * 1024**3,
        power_state="freeze mem disk",
        bootloader="grub",
        initramfs="initramfs-tools",
        candidates=[],
    )


def test_suggested_swap_sizes_has_three_gib_options():
    suggestions = suggested_swap_sizes(8 * 1024**3)
    assert len(suggestions) == 3
    assert [label for label, _size in suggestions] == ["Minimum", "Recommended", "2× RAM"]
    assert [size // (1024**3) for _label, size in suggestions] == [8, 10, 16]


def test_swapfile_slider_marks_match_ram_based_guidance():
    marks = swapfile_slider_marks(8 * 1024**3)
    assert marks == [("Minimum", 8), ("Recommended", 10), ("2× RAM", 16)]


def test_swapfile_plan_restores_create_resize_step_and_fstab_visibility():
    request = SwapFileRequest("/swap.img", 10 * 1024**3)
    plan = build_swapfile_modification_plan(_profile_without_swap(), request)
    assert plan.can_apply
    assert plan.swap_file_request == request
    assert "ensure_swap_file" in [step.id for step in plan.steps]
    assert FSTAB_FILE in plan.planned_files
    assert RESUME_FILE in plan.planned_files
    assert GRUB_FRAGMENT in plan.planned_files


def test_helper_schema_accepts_managed_swapfile_request():
    request = SwapFileRequest("/swap.img", 10 * 1024**3)
    plan = build_swapfile_modification_plan(_profile_without_swap(), request)
    req = plan.to_helper_request(dry_run=True)
    req["request_id"] = "test"
    req["action"] = "validate-plan"
    req["app_version"] = APP_VERSION
    target, swap_req = helper._validate_one_shot_request(req)
    assert target.path == "/swap.img"
    assert swap_req.path == "/swap.img"
    assert swap_req.size_bytes == 10 * 1024**3


def test_helper_schema_rejects_unmanaged_swapfile_path():
    with pytest.raises(ValueError):
        SwapFileRequest("/tmp/swap.img", 8 * 1024**3)


def test_gui_source_contains_restored_controls():
    source = open("ubuntu_hibernate_wizard/ui/wizard_window.py", encoding="utf-8").read()
    assert "swapfile_size_slider" in source
    assert "swapfile_size_manual_input" in source
    assert "btn_swapfile_preset_" in source
    assert "toggle_managed_swapfile" in source
    assert "scale.add_mark" in source
    assert 'Gtk.PositionType.TOP if mark_label == "Recommended" else Gtk.PositionType.BOTTOM' in source
    assert "Recommended is shown above the slider" in source
    assert "2× RAM" in source


def test_validate_plan_for_swapfile_request_is_non_mutating(monkeypatch, capsys):
    request = SwapFileRequest("/swap.img", 10 * 1024**3)
    plan = build_swapfile_modification_plan(_profile_without_swap(), request)
    req = plan.to_helper_request(dry_run=False)
    req["request_id"] = "test-validate"
    req["action"] = "validate-plan"

    def forbidden_begin(*_args, **_kwargs):  # pragma: no cover - should never execute
        raise AssertionError("validate-plan must not create rollback snapshots")

    monkeypatch.setattr(helper.rb.BackupManager, "begin", forbidden_begin)
    assert helper.run_one_shot(req) == 0
    out = capsys.readouterr().out
    assert "Plan is valid" in out
