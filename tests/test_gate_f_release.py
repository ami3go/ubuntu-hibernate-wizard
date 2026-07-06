from pathlib import Path

from ubuntu_hibernate_wizard.constants import APP_VERSION
from ubuntu_hibernate_wizard.services.gate_f_release import (
    build_gate_f_manifest,
    create_manual_record,
    write_manual_record,
)


def _gate_e_report() -> dict:
    return {
        "schema_version": 1,
        "app_version": APP_VERSION,
        "mode": "apply",
        "status": "manual_hibernate_pending",
        "vm_detected": True,
        "virt": "kvm",
        "plan_can_apply": True,
        "target": {"kind": "partition", "path": "/dev/vda3"},
        "steps": [
            {"name": "helper-apply", "status": "passed", "message": "done", "data": {"exit_code": 0}},
            {"name": "manual-hibernate-resume-test", "status": "warning", "message": "pending"},
        ],
        "helper_events": [{"event": "done", "status": "success"}],
    }


def test_gate_f_manifest_ready_when_gate_e_and_manual_record_pass(tmp_path: Path):
    gate_e = tmp_path / "gate-e-apply.json"
    import json
    gate_e.write_text(json.dumps(_gate_e_report()), encoding="utf-8")
    record = create_manual_record(
        gate_e_report_path=gate_e,
        manual_status="passed",
        reboot_performed=True,
        hibernate_attempted=True,
        resumed_successfully=True,
        post_resume_verify_passed=True,
        operator="release-vm",
        notes="ok",
    )
    manual_path = write_manual_record(record, tmp_path / "manual.json")
    manifest = build_gate_f_manifest(gate_e, manual_path)
    assert manifest.status == "release_candidate_ready"
    assert not manifest.blockers


def test_gate_f_manifest_blocks_failed_manual_resume(tmp_path: Path):
    gate_e = tmp_path / "gate-e-apply.json"
    import json
    gate_e.write_text(json.dumps(_gate_e_report()), encoding="utf-8")
    record = create_manual_record(
        gate_e_report_path=gate_e,
        manual_status="failed",
        reboot_performed=True,
        hibernate_attempted=True,
        resumed_successfully=False,
        post_resume_verify_passed=False,
        operator="release-vm",
    )
    manual_path = write_manual_record(record, tmp_path / "manual.json")
    manifest = build_gate_f_manifest(gate_e, manual_path)
    assert manifest.status == "blocked"
    assert any("Manual hibernate/resume status" in b for b in manifest.blockers)


def test_gate_f_manifest_blocks_wrong_gate_e_hash(tmp_path: Path):
    import json
    gate_e = tmp_path / "gate-e-apply.json"
    gate_e.write_text(json.dumps(_gate_e_report()), encoding="utf-8")
    other_gate_e = tmp_path / "other-gate-e.json"
    modified = _gate_e_report()
    modified["virt"] = "qemu"
    other_gate_e.write_text(json.dumps(modified), encoding="utf-8")
    record = create_manual_record(
        gate_e_report_path=other_gate_e,
        manual_status="passed",
        reboot_performed=True,
        hibernate_attempted=True,
        resumed_successfully=True,
        post_resume_verify_passed=True,
        operator="release-vm",
    )
    manual_path = write_manual_record(record, tmp_path / "manual.json")
    manifest = build_gate_f_manifest(gate_e, manual_path)
    assert manifest.status == "blocked"
    assert any("exact Gate E report hash" in b for b in manifest.blockers)
