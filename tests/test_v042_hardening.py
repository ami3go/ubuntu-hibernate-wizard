from pathlib import Path

import pytest

from ubuntu_hibernate_wizard.backend import privileged_helper as helper
from ubuntu_hibernate_wizard.constants import GRUB_FRAGMENT, PROTOCOL_VERSION, RESUME_FILE
from ubuntu_hibernate_wizard.core.parsers import SwapDevice
from ubuntu_hibernate_wizard.services.hibernate_planner import generated_grub_fragment, generated_resume_config
from ubuntu_hibernate_wizard.services.log_exporter import redact_diagnostic_text
from ubuntu_hibernate_wizard.services.swap_detector import classify_swap_targets
from ubuntu_hibernate_wizard.services.system_probe import profile_from_probe_data

UUID = "d76e67b3-404f-461e-a961-7963664d66b3"
RAM = 8 * 1024**3


def test_missing_update_grub_blocks_grub_profile():
    profile = profile_from_probe_data({
        "swapon": "NAME TYPE SIZE USED PRIO\n/dev/nvme0n1p3 partition 17179869184 0 -2\n",
        "swap_details": {"/dev/nvme0n1p3": {"uuid": UUID}},
        "ram_bytes": RAM,
        "power_state": "freeze mem disk",
        "grub_exists": True,
        "update_grub_exists": False,
        "initramfs_tools": True,
        "update_initramfs_exists": True,
    })
    assert profile.bootloader == "unknown"
    assert any("GRUB" in r for r in profile.blocking_reasons)


def test_encrypted_swap_requires_proven_stable_mapping():
    targets = classify_swap_targets(
        [SwapDevice("/dev/mapper/cryptswap", "partition", 16 * 1024**3, 0, -2)],
        RAM,
        {"/dev/mapper/cryptswap": {"uuid": UUID, "encrypted": True}},
    )
    assert targets[0].status == "blocked"
    assert "stable" in targets[0].reasons[0]


def test_btrfs_swap_file_requires_btrfs_map_offset():
    targets = classify_swap_targets(
        [SwapDevice("/swap.img", "file", 16 * 1024**3, 0, -1)],
        RAM,
        {"/swap.img": {"filesystem": "btrfs", "uuid": UUID}},
    )
    assert targets[0].status == "blocked"
    assert "btrfs" in targets[0].reasons[0]


def test_helper_schema_rejects_unknown_top_level_fields():
    target = classify_swap_targets(
        [SwapDevice("/dev/nvme0n1p3", "partition", 16 * 1024**3, 0, -2)],
        RAM,
        {"/dev/nvme0n1p3": {"uuid": UUID}},
    )[0]
    req = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": "test",
        "action": "validate-plan",
        "dry_run": False,
        "app_version": "0.42.0",
        "selected_target": target.to_dict(),
        "rollback": {"mode": "timeshift_or_file_backup"},
        "planned_files": [RESUME_FILE, GRUB_FRAGMENT],
        "steps": ["validate_target", "create_rollback", "write_resume_config", "write_grub_config", "update_initramfs", "update_grub"],
        "unexpected_shell_command": "rm -rf /",
    }
    with pytest.raises(ValueError, match="UNKNOWN_REQUEST_FIELDS"):
        helper._validate_one_shot_request(req)


def test_gui_allows_themed_icon_only_for_system_check_resources():
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    assert "themed:utilities-system-monitor-symbolic" in source
    assert "new_from_icon_name" in source
    assert "set_from_icon_name" in source


def test_diagnostic_redaction_hides_home_and_hostname():
    text = redact_diagnostic_text("Host: lab-pc file=/home/alex/project/config")
    assert "lab-pc" not in text
    assert "/home/alex" not in text
    assert "/home/<user>" in text


def test_golden_configs_are_exact_for_partition_and_file():
    part = classify_swap_targets(
        [SwapDevice("/dev/nvme0n1p3", "partition", 16 * 1024**3, 0, -2)],
        RAM,
        {"/dev/nvme0n1p3": {"uuid": UUID}},
    )[0]
    swap_file = classify_swap_targets(
        [SwapDevice("/swap.img", "file", 16 * 1024**3, 0, -1)],
        RAM,
        {"/swap.img": {"filesystem": "ext4", "uuid": UUID, "resume_offset": 5986304}},
    )[0]
    assert generated_resume_config(part) == f"RESUME=UUID={UUID}\n"
    assert generated_resume_config(swap_file) == f"RESUME=UUID={UUID} resume_offset=5986304\n"
    assert generated_grub_fragment(part) == (
        "# BEGIN UBUNTU HIBERNATE WIZARD\n"
        "# Managed by Ubuntu Hibernate Wizard. Manual edits inside this block may be overwritten.\n"
        "uhw_add_kernel_param() {\n"
        "  case \" ${GRUB_CMDLINE_LINUX_DEFAULT} \" in\n"
        "    *\" $1 \"*) ;;\n"
        "    *) GRUB_CMDLINE_LINUX_DEFAULT=\"${GRUB_CMDLINE_LINUX_DEFAULT} $1\" ;;\n"
        "  esac\n"
        "}\n"
        f"uhw_add_kernel_param \"resume=UUID={UUID}\"\n"
        "unset -f uhw_add_kernel_param\n"
        "# END UBUNTU HIBERNATE WIZARD\n"
    )
    assert f'uhw_add_kernel_param "resume_offset=5986304"' in generated_grub_fragment(swap_file)


def _valid_helper_request(target):
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": "test",
        "action": "validate-plan",
        "dry_run": False,
        "app_version": helper.APP_VERSION,
        "selected_target": target.to_dict(),
        "rollback": {"mode": "timeshift_or_file_backup"},
        "planned_files": [RESUME_FILE, GRUB_FRAGMENT],
        "steps": ["validate_target", "create_rollback", "write_resume_config", "write_grub_config", "update_initramfs", "update_grub"],
    }


def test_helper_schema_rejects_bad_version_and_duplicate_steps():
    target = classify_swap_targets(
        [SwapDevice("/dev/nvme0n1p3", "partition", 16 * 1024**3, 0, -2)],
        RAM,
        {"/dev/nvme0n1p3": {"uuid": UUID}},
    )[0]
    req = _valid_helper_request(target)
    req["app_version"] = "0.0.0"
    with pytest.raises(ValueError, match="BAD_APP_VERSION"):
        helper._validate_one_shot_request(req)
    req = _valid_helper_request(target)
    req["steps"] = req["steps"] + ["update_grub"]
    with pytest.raises(ValueError, match="DUPLICATE_STEP_ID"):
        helper._validate_one_shot_request(req)


def test_helper_schema_rejects_unknown_selected_target_fields():
    target = classify_swap_targets(
        [SwapDevice("/dev/nvme0n1p3", "partition", 16 * 1024**3, 0, -2)],
        RAM,
        {"/dev/nvme0n1p3": {"uuid": UUID}},
    )[0]
    req = _valid_helper_request(target)
    req["selected_target"]["shell"] = "rm -rf /"
    with pytest.raises(ValueError, match="UNKNOWN_TARGET_FIELDS"):
        helper._validate_one_shot_request(req)
