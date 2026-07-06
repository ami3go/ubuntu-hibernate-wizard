"""Gate F release-candidate evidence checks.

Gate F does not perform system mutation.  It consumes the Gate E disposable-VM
apply report plus a human manual hibernate/resume record and produces a release
candidate manifest.  The goal is to keep the public release decision auditable
without weakening the Gate E safety guard.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal

from ubuntu_hibernate_wizard.constants import APP_VERSION
from ubuntu_hibernate_wizard.services.log_exporter import redact_diagnostic_text

ManualStatus = Literal["passed", "failed", "blocked"]
GateFStatus = Literal["release_candidate_ready", "blocked"]

REQUIRED_MANUAL_TRUE_FIELDS = (
    "reboot_performed",
    "hibernate_attempted",
    "resumed_successfully",
    "post_resume_verify_passed",
)


class GateFError(RuntimeError):
    """Raised when a Gate F input file is malformed or unsafe to trust."""


@dataclass(slots=True)
class GateFCheck:
    name: str
    status: Literal["passed", "failed", "warning"]
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ManualHibernateRecord:
    schema_version: int
    app_version: str
    gate_e_report_sha256: str
    manual_status: ManualStatus
    reboot_performed: bool
    hibernate_attempted: bool
    resumed_successfully: bool
    post_resume_verify_passed: bool
    operator: str
    recorded_at: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return json.loads(redact_diagnostic_text(json.dumps(asdict(self), sort_keys=True)))


@dataclass(slots=True)
class GateFManifest:
    schema_version: int
    app_version: str
    generated_at: str
    status: GateFStatus
    gate_e_report_sha256: str
    manual_record_sha256: str
    checks: list[GateFCheck]
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    release_note: str = (
        "Gate F means the release-candidate evidence is complete. It does not "
        "guarantee hibernation on every hardware configuration."
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        text = redact_diagnostic_text(json.dumps(data, sort_keys=True))
        return json.loads(text)


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: str | os.PathLike[str]) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise GateFError(f"could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GateFError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GateFError(f"{path} must contain a JSON object")
    return data


def _safe_text(value: str, *, max_len: int = 4000) -> str:
    return redact_diagnostic_text(str(value or "").strip()[:max_len])


def create_manual_record(
    *,
    gate_e_report_path: str | os.PathLike[str],
    manual_status: ManualStatus,
    reboot_performed: bool,
    hibernate_attempted: bool,
    resumed_successfully: bool,
    post_resume_verify_passed: bool,
    operator: str,
    notes: str = "",
) -> ManualHibernateRecord:
    """Create a redaction-ready manual hibernate/resume evidence record."""
    if manual_status not in {"passed", "failed", "blocked"}:
        raise GateFError("manual_status must be passed, failed, or blocked")
    operator = _safe_text(operator, max_len=120)
    if not operator:
        raise GateFError("operator is required for Gate F manual evidence")
    return ManualHibernateRecord(
        schema_version=1,
        app_version=APP_VERSION,
        gate_e_report_sha256=sha256_file(gate_e_report_path),
        manual_status=manual_status,
        reboot_performed=bool(reboot_performed),
        hibernate_attempted=bool(hibernate_attempted),
        resumed_successfully=bool(resumed_successfully),
        post_resume_verify_passed=bool(post_resume_verify_passed),
        operator=operator,
        recorded_at=now_utc(),
        notes=_safe_text(notes),
    )


def write_manual_record(record: ManualHibernateRecord, path: str | os.PathLike[str]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def _helper_apply_passed(gate_e: dict[str, Any]) -> bool:
    for step in gate_e.get("steps", []):
        if isinstance(step, dict) and step.get("name") == "helper-apply":
            return step.get("status") == "passed" and step.get("data", {}).get("exit_code") == 0
    # Backward-compatible fallback: look at events if the step name is missing.
    events = gate_e.get("helper_events", [])
    return any(isinstance(e, dict) and e.get("status") == "success" for e in events)


def _check_gate_e_report(gate_e: dict[str, Any], gate_e_hash: str, checks: list[GateFCheck], blockers: list[str]) -> None:
    def add(name: str, ok: bool, message: str, data: dict[str, Any] | None = None) -> None:
        checks.append(GateFCheck(name, "passed" if ok else "failed", message, data or {}))
        if not ok:
            blockers.append(message)

    add("gate-e-mode", gate_e.get("mode") == "apply", "Gate E report must be from mode=apply", {"mode": gate_e.get("mode")})
    add(
        "gate-e-status",
        gate_e.get("status") == "manual_hibernate_pending",
        "Gate E apply report must have status manual_hibernate_pending",
        {"status": gate_e.get("status")},
    )
    add("gate-e-app-version", gate_e.get("app_version") == APP_VERSION, "Gate E report version must match current package", {"report_version": gate_e.get("app_version"), "current_version": APP_VERSION})
    add("gate-e-vm", bool(gate_e.get("vm_detected")), "Gate E apply must have been executed in a detected VM", {"virt": gate_e.get("virt")})
    add("gate-e-plan", bool(gate_e.get("plan_can_apply")), "Gate E report must show a selectable apply plan")
    add("gate-e-helper-apply", _helper_apply_passed(gate_e), "Gate E helper apply step must have succeeded")
    target = gate_e.get("target") or {}
    add("gate-e-target", target.get("kind") in {"partition", "file"} and bool(target.get("path")), "Gate E target must be an existing swap partition or file", {"target_kind": target.get("kind"), "target_path": target.get("path")})
    # Store hash presence as a positive audit marker.
    checks.append(GateFCheck("gate-e-report-hash", "passed", "Gate E report hash calculated", {"sha256": gate_e_hash}))


def _check_manual_record(manual: dict[str, Any], manual_hash: str, gate_e_hash: str, checks: list[GateFCheck], blockers: list[str]) -> None:
    def add(name: str, ok: bool, message: str, data: dict[str, Any] | None = None) -> None:
        checks.append(GateFCheck(name, "passed" if ok else "failed", message, data or {}))
        if not ok:
            blockers.append(message)

    add("manual-schema", manual.get("schema_version") == 1, "Manual record schema_version must be 1")
    add("manual-app-version", manual.get("app_version") == APP_VERSION, "Manual record version must match current package", {"record_version": manual.get("app_version"), "current_version": APP_VERSION})
    add("manual-report-link", manual.get("gate_e_report_sha256") == gate_e_hash, "Manual record must reference this exact Gate E report hash", {"expected": gate_e_hash, "actual": manual.get("gate_e_report_sha256")})
    add("manual-status", manual.get("manual_status") == "passed", "Manual hibernate/resume status must be passed", {"manual_status": manual.get("manual_status")})
    for field_name in REQUIRED_MANUAL_TRUE_FIELDS:
        add(f"manual-{field_name.replace('_', '-')}", manual.get(field_name) is True, f"Manual record field {field_name} must be true")
    add("manual-operator", bool(str(manual.get("operator") or "").strip()), "Manual record must include an operator name or release identifier")
    add("manual-record-hash", True, "Manual record hash calculated", {"sha256": manual_hash})


def build_gate_f_manifest(gate_e_report_path: str | os.PathLike[str], manual_record_path: str | os.PathLike[str]) -> GateFManifest:
    gate_e_hash = sha256_file(gate_e_report_path)
    manual_hash = sha256_file(manual_record_path)
    gate_e = _load_json(gate_e_report_path)
    manual = _load_json(manual_record_path)
    checks: list[GateFCheck] = []
    blockers: list[str] = []
    warnings: list[str] = []

    try:
        _check_gate_e_report(gate_e, gate_e_hash, checks, blockers)
        _check_manual_record(manual, manual_hash, gate_e_hash, checks, blockers)
    except GateFError as exc:
        blockers.append(str(exc))
        checks.append(GateFCheck("gate-f-input", "failed", str(exc)))

    if not gate_e.get("helper_events"):
        warnings.append("Gate E report does not include helper event detail")
        checks.append(GateFCheck("helper-events-present", "warning", warnings[-1]))

    status: GateFStatus = "release_candidate_ready" if not blockers else "blocked"
    return GateFManifest(
        schema_version=1,
        app_version=APP_VERSION,
        generated_at=now_utc(),
        status=status,
        gate_e_report_sha256=gate_e_hash,
        manual_record_sha256=manual_hash,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
    )


def write_gate_f_manifest(manifest: GateFManifest, path: str | os.PathLike[str]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def render_gate_f_summary(manifest: GateFManifest, path: str | os.PathLike[str] | None = None) -> str:
    lines = [
        "Gate F release-candidate evidence check",
        f"Status: {manifest.status}",
        f"App version: {manifest.app_version}",
    ]
    if path:
        lines.append(f"Manifest: {path}")
    if manifest.blockers:
        lines.append("Blockers:")
        lines.extend(f"- {b}" for b in manifest.blockers)
    if manifest.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {w}" for w in manifest.warnings)
    lines.append("Checks:")
    lines.extend(f"- [{check.status}] {check.name}: {check.message}" for check in manifest.checks)
    if manifest.status == "release_candidate_ready":
        lines.append("Next: tag this as a release candidate only after package install/removal smoke tests pass on a clean VM.")
    return redact_diagnostic_text("\n".join(lines))
