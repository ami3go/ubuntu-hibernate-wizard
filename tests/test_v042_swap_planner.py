from ubuntu_hibernate_wizard.core.parsers import SwapDevice, parse_btrfs_map_swapfile_offset
from ubuntu_hibernate_wizard.services.swap_detector import classify_swap_targets
from ubuntu_hibernate_wizard.services.swap_target_model import SystemProfile
from ubuntu_hibernate_wizard.services.hibernate_planner import (
    build_modification_plan, generated_grub_fragment, generated_resume_config,
)

UUID = "d76e67b3-404f-461e-a961-7963664d66b3"
RAM = 8 * 1024**3


def test_partition_preferred_over_valid_swap_file():
    devices = [
        SwapDevice("/swap.img", "file", 32 * 1024**3, 0, -1),
        SwapDevice("/dev/nvme0n1p3", "partition", 16 * 1024**3, 0, -2),
    ]
    targets = classify_swap_targets(devices, RAM, {
        "/swap.img": {"filesystem": "ext4", "uuid": UUID, "resume_offset": 5986304},
        "/dev/nvme0n1p3": {"uuid": "aaaaaaaa-404f-461e-a961-7963664d66b3"},
    })
    part = next(t for t in targets if t.kind == "partition")
    file = next(t for t in targets if t.kind == "file")
    assert part.status == "recommended"
    assert file.status == "valid_option"


def test_zram_only_is_blocked():
    targets = classify_swap_targets([SwapDevice("/dev/zram0", "partition", 32 * 1024**3, 0, 100)], RAM, {})
    assert targets[0].status == "blocked"
    assert "zram" in targets[0].reasons[0]


def test_small_swap_file_is_warning_not_selectable():
    targets = classify_swap_targets([SwapDevice("/swap.img", "file", 4 * 1024**3, 0, -1)], RAM, {
        "/swap.img": {"filesystem": "ext4", "uuid": UUID, "resume_offset": 5986304},
    })
    assert targets[0].status == "warning_option"
    assert not targets[0].selectable


def test_generated_config_partition_has_no_resume_offset():
    target = classify_swap_targets([SwapDevice("/dev/nvme0n1p3", "partition", 16 * 1024**3, 0, -2)], RAM, {
        "/dev/nvme0n1p3": {"uuid": UUID},
    })[0]
    assert "resume_offset" not in generated_resume_config(target)
    assert "resume=UUID=" + UUID in generated_grub_fragment(target)
    assert "resume_offset" not in generated_grub_fragment(target)


def test_generated_config_swap_file_has_resume_offset():
    target = classify_swap_targets([SwapDevice("/swap.img", "file", 16 * 1024**3, 0, -1)], RAM, {
        "/swap.img": {"filesystem": "ext4", "uuid": UUID, "resume_offset": 5986304},
    })[0]
    assert generated_resume_config(target) == f"RESUME=UUID={UUID} resume_offset=5986304\n"
    assert "resume_offset=5986304" in generated_grub_fragment(target)


def test_plan_blocks_existing_conflicting_resume():
    target = classify_swap_targets([SwapDevice("/swap.img", "file", 16 * 1024**3, 0, -1)], RAM, {
        "/swap.img": {"filesystem": "ext4", "uuid": UUID, "resume_offset": 5986304},
    })[0]
    profile = SystemProfile(
        ram_bytes=RAM,
        power_state="freeze mem disk",
        bootloader="grub",
        initramfs="initramfs-tools",
        cmdline="quiet splash resume=UUID=aaaaaaaa-404f-461e-a961-7963664d66b3 resume_offset=1",
        candidates=[target],
    )
    plan = build_modification_plan(profile, target)
    assert not plan.can_apply
    assert any("differs" in r for r in plan.blocking_reasons)


def test_btrfs_offset_parser_accepts_numeric_only():
    assert parse_btrfs_map_swapfile_offset("123456\n") == 123456


def test_swapfile_offset_permission_denied_uses_matching_existing_resume_config():
    from ubuntu_hibernate_wizard.services.system_probe import profile_from_probe_data, probe_swap_details_from_data

    data = {
        "fixture_name": "existing_resume_permission_denied",
        "swapon": "NAME TYPE SIZE USED PRIO\n/swap.img file 25769799680 0 -1\n",
        "ram_bytes": RAM,
        "power_state": "freeze mem disk\n",
        "bootloader": "grub",
        "initramfs": "initramfs-tools",
        "fstab": "/swap.img none swap sw 0 0\n",
        "cmdline": f"quiet splash resume=UUID={UUID} resume_offset=15464448",
        "initramfs_resume": f"RESUME=UUID={UUID} resume_offset=15464448\n",
        "swap_details": {
            "/swap.img": {
                "filesystem": "ext4",
                "uuid": UUID,
                "backing_device": "/dev/nvme0n1p2",
                "offset_error": "open: Permission denied",
            }
        },
    }
    data["swap_details"] = probe_swap_details_from_data(data)
    profile = profile_from_probe_data(data)
    target = profile.recommended_target
    assert target is not None
    assert target.path == "/swap.img"
    assert target.resume_offset == 15464448
    assert target.status == "recommended"
    assert not profile.blocking_reasons
    assert any("existing kernel/initramfs resume_offset" in w for w in target.warnings)


def test_swapfile_offset_permission_denied_stays_blocked_on_resume_uuid_mismatch():
    from ubuntu_hibernate_wizard.services.system_probe import profile_from_probe_data, probe_swap_details_from_data

    other_uuid = "aaaaaaaa-404f-461e-a961-7963664d66b3"
    data = {
        "fixture_name": "existing_resume_permission_denied_mismatch",
        "swapon": "NAME TYPE SIZE USED PRIO\n/swap.img file 25769799680 0 -1\n",
        "ram_bytes": RAM,
        "power_state": "freeze mem disk\n",
        "bootloader": "grub",
        "initramfs": "initramfs-tools",
        "fstab": "/swap.img none swap sw 0 0\n",
        "cmdline": f"quiet splash resume=UUID={other_uuid} resume_offset=15464448",
        "initramfs_resume": f"RESUME=UUID={other_uuid} resume_offset=15464448\n",
        "swap_details": {
            "/swap.img": {
                "filesystem": "ext4",
                "uuid": UUID,
                "backing_device": "/dev/nvme0n1p2",
                "offset_error": "open: Permission denied",
            }
        },
    }
    data["swap_details"] = probe_swap_details_from_data(data)
    profile = profile_from_probe_data(data)
    target = profile.candidates[0]
    assert target.resume_offset is None
    assert target.status == "blocked"
    assert any("resume offset" in r.lower() for r in target.reasons)
