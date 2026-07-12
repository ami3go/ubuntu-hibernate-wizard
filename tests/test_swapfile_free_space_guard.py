from pathlib import Path

from ubuntu_hibernate_wizard.services.hibernate_planner import (
    DEFAULT_SWAPFILE_PATH,
    GIB,
    MIN_ROOT_FREE_AFTER_SWAPFILE_BYTES,
    SwapFileRequest,
    build_swapfile_modification_plan,
    swapfile_allocation_required_bytes,
    swapfile_free_space_problem,
)
from ubuntu_hibernate_wizard.services.swap_target_model import SwapTarget, SystemProfile


def _profile(*, ram_gib: int = 32, free_gib: int = 64, existing_swap_gib: int = 8) -> SystemProfile:
    candidates = []
    if existing_swap_gib:
        candidates.append(SwapTarget(
            id=DEFAULT_SWAPFILE_PATH,
            kind="file",
            path=DEFAULT_SWAPFILE_PATH,
            size_bytes=existing_swap_gib * GIB,
            status="warning_option" if existing_swap_gib < ram_gib else "recommended",
            title="Swap file /swap.img",
            detail=f"{existing_swap_gib} GiB swap",
            uuid="d76e67b3-404f-461e-a961-7963664d66b3",
            resume_offset=123,
        ))
    return SystemProfile(
        ram_bytes=ram_gib * GIB,
        root_total_bytes=100 * GIB,
        root_free_bytes=free_gib * GIB,
        power_state="freeze mem disk",
        bootloader="grub",
        initramfs="initramfs-tools",
        candidates=candidates,
    )


def test_swapfile_resize_requires_full_new_file_plus_reserve() -> None:
    profile = _profile(ram_gib=32, free_gib=30, existing_swap_gib=8)
    request = SwapFileRequest(DEFAULT_SWAPFILE_PATH, 33 * GIB)
    assert swapfile_allocation_required_bytes(profile, request) == 33 * GIB
    problem = swapfile_free_space_problem(profile, request)
    assert problem is not None
    assert "Not enough free space" in problem
    assert "34.0 GiB" in problem


def test_swapfile_plan_blocks_when_free_space_is_insufficient() -> None:
    profile = _profile(ram_gib=32, free_gib=30, existing_swap_gib=8)
    plan = build_swapfile_modification_plan(profile, SwapFileRequest(DEFAULT_SWAPFILE_PATH, 33 * GIB))
    assert not plan.can_apply
    assert any("Not enough free space" in reason for reason in plan.blocking_reasons)


def test_swapfile_plan_allows_when_free_space_is_sufficient() -> None:
    profile = _profile(ram_gib=32, free_gib=40, existing_swap_gib=8)
    plan = build_swapfile_modification_plan(profile, SwapFileRequest(DEFAULT_SWAPFILE_PATH, 33 * GIB))
    assert plan.can_apply


def test_swapfile_plan_blocks_size_smaller_than_ram() -> None:
    profile = _profile(ram_gib=32, free_gib=40, existing_swap_gib=8)
    plan = build_swapfile_modification_plan(profile, SwapFileRequest(DEFAULT_SWAPFILE_PATH, 16 * GIB))
    assert not plan.can_apply
    assert any("smaller than detected RAM" in reason for reason in plan.blocking_reasons)


def test_existing_same_size_does_not_need_allocation_space() -> None:
    profile = _profile(ram_gib=32, free_gib=1, existing_swap_gib=33)
    request = SwapFileRequest(DEFAULT_SWAPFILE_PATH, 33 * GIB)
    assert swapfile_allocation_required_bytes(profile, request) == 0
    assert swapfile_free_space_problem(profile, request) is None


def test_free_space_reserve_constant_is_one_gib() -> None:
    assert MIN_ROOT_FREE_AFTER_SWAPFILE_BYTES == GIB
