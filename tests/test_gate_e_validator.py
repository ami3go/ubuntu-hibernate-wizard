import os

from ubuntu_hibernate_wizard.services.gate_e_validator import (
    GATE_E_ACK_TEXT,
    GateEError,
    require_disposable_vm_ack,
    vm_detected_from_virt,
    run_gate_e,
)


def test_gate_e_detects_real_vm_names_and_blocks_containers():
    assert vm_detected_from_virt("kvm")
    assert vm_detected_from_virt("qemu")
    assert not vm_detected_from_virt("none")
    assert not vm_detected_from_virt("docker")


def test_gate_e_apply_requires_exact_ack():
    try:
        require_disposable_vm_ack("apply", None, virt="kvm")
    except GateEError as exc:
        assert GATE_E_ACK_TEXT in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Gate E apply without acknowledgement was not blocked")


def test_gate_e_apply_blocks_non_vm_even_with_ack():
    try:
        require_disposable_vm_ack("apply", GATE_E_ACK_TEXT, virt="none")
    except GateEError as exc:
        assert "disposable VM" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Gate E physical apply was not blocked")


def test_gate_e_non_apply_does_not_require_ack():
    require_disposable_vm_ack("preflight", None, virt="none")
    require_disposable_vm_ack("dry-run", None, virt="none")


def test_gate_e_run_apply_without_ack_returns_blocked(monkeypatch):
    # Use a minimal fake live plan so the test verifies the safety guard rather
    # than depending on the host/container hibernation configuration.
    from ubuntu_hibernate_wizard.services import gate_e_validator as gev
    from ubuntu_hibernate_wizard.core.parsers import SwapDevice
    from ubuntu_hibernate_wizard.services.system_probe import profile_from_probe_data
    from ubuntu_hibernate_wizard.services.hibernate_planner import build_modification_plan

    uuid = "d76e67b3-404f-461e-a961-7963664d66b3"
    raw = {
        "virt": "kvm",
        "swapon": "NAME TYPE SIZE USED PRIO\n/dev/nvme0n1p3 partition 17179869184 0 -2\n",
        "swap_details": {"/dev/nvme0n1p3": {"uuid": uuid}},
        "ram_bytes": 8 * 1024**3,
        "power_state": "freeze mem disk",
        "bootloader": "grub",
        "initramfs": "initramfs-tools",
    }
    profile = profile_from_probe_data(raw)
    target = profile.recommended_target
    plan = build_modification_plan(profile, target)
    monkeypatch.setattr(gev, "build_live_plan", lambda: (profile, target, plan))
    report = run_gate_e("apply")
    assert report.status == "blocked"
    assert any("ack" in step.message or "requires" in step.message for step in report.steps)
