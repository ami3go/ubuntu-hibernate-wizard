"""Gate E disposable-VM validation support.

Gate E is intentionally separate from the normal GUI flow.  It is a developer
and release-engineering tool for validating real privileged apply behavior in a
throw-away Ubuntu VM.  It never marks the product as fully release-ready by
itself because the final hibernate/resume cycle still requires a manual reboot
and manual hibernate test on the VM.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import os
import subprocess
from contextlib import redirect_stdout
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal

from ubuntu_hibernate_wizard.constants import APP_VERSION, LOG_DIR
from ubuntu_hibernate_wizard.services.hibernate_planner import ModificationPlan, build_modification_plan
from ubuntu_hibernate_wizard.services.log_exporter import redact_diagnostic_text
from ubuntu_hibernate_wizard.services.system_probe import probe_current_system, profile_from_probe_data
from ubuntu_hibernate_wizard.services.swap_target_model import SystemProfile, SwapTarget

GateEMode = Literal["preflight", "validate-plan", "dry-run", "apply"]
GATE_E_ACK_TEXT = "I_UNDERSTAND_THIS_IS_A_DISPOSABLE_VM"
UNSAFE_VIRT_VALUES = {"", "none", "unknown", "docker", "podman", "lxc", "systemd-nspawn", "container"}


class GateEError(RuntimeError):
    """Raised when Gate E validation is intentionally blocked."""


@dataclass(slots=True)
class GateEStep:
    name: str
    status: Literal["passed", "failed", "skipped", "warning"]
    message: str
    data: dict = field(default_factory=dict)


@dataclass(slots=True)
class GateEReport:
    schema_version: int
    app_version: str
    mode: GateEMode
    started_at: str
    completed_at: str | None = None
    status: Literal["passed", "failed", "blocked", "manual_hibernate_pending"] = "blocked"
    host: str = "<redacted-host>"
    euid: int = -1
    vm_detected: bool = False
    virt: str = "unknown"
    target: dict | None = None
    plan_can_apply: bool = False
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    steps: list[GateEStep] = field(default_factory=list)
    helper_events: list[dict] = field(default_factory=list)
    report_note: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        # Defense in depth: do not persist raw hostnames/user paths if helper or
        # command output placed them inside message fields.
        text = redact_diagnostic_text(json.dumps(data, sort_keys=True))
        return json.loads(text)


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def vm_detected_from_virt(virt: str | None) -> bool:
    return (virt or "unknown").strip().lower() not in UNSAFE_VIRT_VALUES


def require_disposable_vm_ack(mode: GateEMode, ack: str | None, *, allow_physical: bool = False, virt: str | None = None) -> None:
    """Block dangerous Gate E operations unless the operator accepts the risk."""
    if mode != "apply":
        return
    if ack != GATE_E_ACK_TEXT:
        raise GateEError(
            "Gate E real apply requires --gate-e-ack " + GATE_E_ACK_TEXT
        )
    if not allow_physical and not vm_detected_from_virt(virt):
        raise GateEError(
            "Gate E real apply is blocked because this does not look like a disposable VM. "
            "Use a throw-away Ubuntu VM; do not use a developer or daily-driver machine."
        )


def _selected_target(profile: SystemProfile) -> SwapTarget | None:
    return profile.recommended_target


def build_live_plan() -> tuple[SystemProfile, SwapTarget | None, ModificationPlan | None]:
    profile = profile_from_probe_data(probe_current_system())
    target = _selected_target(profile)
    if target is None:
        return profile, None, None
    return profile, target, build_modification_plan(profile, target)



def _base_report(mode: GateEMode, profile: SystemProfile, target: SwapTarget | None, plan: ModificationPlan | None) -> GateEReport:
    virt = str(profile.raw.get("virt") or "unknown")
    report = GateEReport(
        schema_version=1,
        app_version=APP_VERSION,
        mode=mode,
        started_at=now_utc(),
        host="<redacted-host>",
        euid=os.geteuid() if hasattr(os, "geteuid") else -1,
        vm_detected=vm_detected_from_virt(virt),
        virt=virt,
        target=target.to_dict() if target else None,
        plan_can_apply=bool(plan and plan.can_apply),
        blockers=list(plan.blocking_reasons if plan else profile.blocking_reasons),
        warnings=list(plan.warnings if plan else []),
        report_note=(
            "Automated Gate E can validate real apply mechanics in a disposable VM. "
            "A human must still reboot the VM, run a hibernate/resume test, and record the result."
        ),
    )
    return report


def _command_available(argv: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=15)
        msg = (r.stdout or r.stderr or "").strip()
        return r.returncode == 0, msg
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def _preflight_steps(report: GateEReport, profile: SystemProfile, plan: ModificationPlan | None) -> None:
    report.steps.append(GateEStep(
        "environment-is-vm",
        "passed" if report.vm_detected else "warning",
        f"systemd-detect-virt reported {report.virt!r}",
    ))
    report.steps.append(GateEStep(
        "supported-boot-stack",
        "passed" if profile.supported_boot_stack else "failed",
        f"bootloader={profile.bootloader}, initramfs={profile.initramfs}",
    ))
    report.steps.append(GateEStep(
        "hibernate-kernel-state",
        "passed" if profile.has_hibernate_kernel_support else "failed",
        f"/sys/power/state={profile.power_state.strip()!r}",
    ))
    report.steps.append(GateEStep(
        "swap-target",
        "passed" if report.target and report.plan_can_apply else "failed",
        "recommended target is selectable" if report.target and report.plan_can_apply else "no selectable hibernation target",
        {"target": report.target or {}},
    ))
    for name, argv in (
        ("update-initramfs", ["update-initramfs", "--help"]),
        ("update-grub", ["update-grub", "--help"]),
        ("swapon", ["swapon", "--show", "--bytes"]),
    ):
        ok, msg = _command_available(argv)
        report.steps.append(GateEStep(
            f"tool-{name}",
            "passed" if ok else "failed",
            msg.splitlines()[0] if msg else ("available" if ok else "not available"),
        ))
    if plan is not None:
        report.steps.append(GateEStep(
            "managed-files-only",
            "passed" if set(plan.planned_files) == {
                "/etc/initramfs-tools/conf.d/resume",
                "/etc/default/grub.d/hibernate-wizard.cfg",
            } else "failed",
            ", ".join(plan.planned_files),
        ))


def _parse_helper_events(text: str) -> list[dict]:
    events: list[dict] = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                events.append(item)
        except json.JSONDecodeError:
            events.append({"event": "unparsed-output", "message": line})
    return events


def _run_helper_direct(request: dict) -> tuple[int, list[dict]]:
    """Run the real one-shot helper implementation in-process as root.

    This is used only by Gate E CLI execution.  It avoids relying on a graphical
    polkit agent during scripted VM validation while still exercising the same
    helper validation and mutation code path.
    """
    if os.geteuid() != 0:
        raise GateEError("Gate E helper validation/apply must be run as root inside the disposable VM")
    from ubuntu_hibernate_wizard.backend import privileged_helper

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = privileged_helper.run_one_shot(request)
    return code, _parse_helper_events(buf.getvalue())


def run_gate_e(
    mode: GateEMode,
    *,
    ack: str | None = None,
    allow_physical: bool = False,
) -> GateEReport:
    """Run one Gate E validation phase and return a redaction-ready report."""
    profile, target, plan = build_live_plan()
    report = _base_report(mode, profile, target, plan)
    _preflight_steps(report, profile, plan)

    try:
        require_disposable_vm_ack(mode, ack, allow_physical=allow_physical, virt=report.virt)
        if plan is None or target is None:
            raise GateEError("No selectable hibernation target is available")
        if not plan.can_apply:
            raise GateEError("Plan is blocked: " + "; ".join(plan.blocking_reasons))

        if mode == "preflight":
            report.status = "passed" if report.plan_can_apply else "blocked"
            return report

        request = plan.to_helper_request(dry_run=(mode == "dry-run"))
        if mode == "validate-plan":
            request["action"] = "validate-plan"
        elif mode == "apply":
            request["dry_run"] = False
        elif mode != "dry-run":
            raise GateEError(f"Unknown Gate E mode: {mode}")

        code, events = _run_helper_direct(request)
        report.helper_events = events
        final_msg = events[-1].get("message", "helper returned") if events else "helper produced no events"
        report.steps.append(GateEStep(
            f"helper-{mode}",
            "passed" if code == 0 else "failed",
            final_msg,
            {"exit_code": code},
        ))
        if code != 0:
            report.status = "failed"
        elif mode == "apply":
            report.status = "manual_hibernate_pending"
            report.steps.append(GateEStep(
                "manual-hibernate-resume-test",
                "warning",
                "Reboot the VM, attempt hibernation, resume it, then record the manual result.",
            ))
        else:
            report.status = "passed"
    except GateEError as exc:
        report.status = "blocked"
        report.steps.append(GateEStep("gate-e-guard", "failed", str(exc)))
    except Exception as exc:  # noqa: BLE001
        report.status = "failed"
        report.steps.append(GateEStep("unexpected-error", "failed", str(exc)))
    finally:
        report.completed_at = now_utc()
    return report


def default_report_dir() -> Path:
    if os.geteuid() == 0:
        return Path(LOG_DIR) / "gate-e"
    return Path.home() / ".cache" / "ubuntu-hibernate-wizard" / "gate-e"


def write_report(report: GateEReport, *, report_dir: str | Path | None = None, report_path: str | Path | None = None) -> Path:
    data = report.to_dict()
    if report_path is None:
        directory = Path(report_dir) if report_dir is not None else default_report_dir()
        directory.mkdir(parents=True, exist_ok=True)
        stamp = report.started_at.replace(":", "").replace("+00:00", "Z")
        report_path = directory / f"gate-e-{report.mode}-{stamp}.json"
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def render_text_summary(report: GateEReport, path: Path | None = None) -> str:
    lines = [
        f"Gate E mode: {report.mode}",
        f"Status: {report.status}",
        f"App version: {report.app_version}",
        f"Virtualization: {report.virt} (vm_detected={report.vm_detected})",
        f"Plan can apply: {report.plan_can_apply}",
    ]
    if path:
        lines.append(f"JSON report: {path}")
    if report.target:
        lines.append(f"Target: {report.target.get('kind')} {report.target.get('path')}")
    if report.blockers:
        lines.append("Blockers:")
        lines.extend(f"- {b}" for b in report.blockers)
    lines.append("Steps:")
    lines.extend(f"- [{step.status}] {step.name}: {step.message}" for step in report.steps)
    if report.status == "manual_hibernate_pending":
        lines.append("Next: reboot the disposable VM, run a manual hibernate/resume test, then keep the report with the release notes.")
    return redact_diagnostic_text("\n".join(lines))
