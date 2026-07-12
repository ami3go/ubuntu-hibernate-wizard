"""GUI-side controller and helper client for Ubuntu Hibernate Wizard v0.42.

v0.42+ supports existing active swap targets and a controlled managed-swapfile
create/resize path.  Real system changes are sent to the narrow helper protocol;
dry-run and fake-system modes never write system files.

Apply log vocabulary includes update-initramfs -u and update-grub because those
fixed helper commands are part of the reviewed plan.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ubuntu_hibernate_wizard.constants import HELPER_PATH, PROTOCOL_VERSION
from ubuntu_hibernate_wizard.services.hibernate_planner import (
    ModificationPlan, SwapFileRequest, build_modification_plan, build_swapfile_modification_plan,
)
from ubuntu_hibernate_wizard.services.log_exporter import build_diagnostic_report, write_diagnostic_zip
from ubuntu_hibernate_wizard.services.system_probe import load_fake_system, profile_from_probe_data, probe_current_system
from ubuntu_hibernate_wizard.services.swap_target_model import SwapTarget, SystemProfile, format_bytes_gib

BACKUP_DIR_BASE = "/var/backups/ubuntu-hibernate-wizard"
ProgressCB = Callable[[float | int, str], None]

CONFIGURATION_RECOVERABLE_BLOCKERS = {
    "No existing active disk swap target is usable for hibernation",
}


@dataclass
class DetectInfo:
    """Compatibility object used by the GTK view layer."""

    rows: list[tuple[str, str, str, str]] = field(default_factory=list)
    secure_boot: bool = False
    ram_bytes: int = 16 * 1024**3
    hard_stop: bool = False
    profile: SystemProfile | None = None
    candidates: list[SwapTarget] = field(default_factory=list)

    @property
    def recommended_target(self) -> SwapTarget | None:
        return self.profile.recommended_target if self.profile else None

    @property
    def configuration_blocking_reasons(self) -> list[str]:
        """Blockers that really prevent opening Configuration.

        A missing/too-small existing swap target must not block Configuration:
        the Configuration page is where the user can create or resize the
        managed /swap.img file.
        """
        if self.profile is None:
            return ["System profile is unavailable"]
        return [
            reason for reason in self.profile.blocking_reasons
            if reason not in CONFIGURATION_RECOVERABLE_BLOCKERS
        ]

    @property
    def can_continue_to_configuration(self) -> bool:
        return not self.configuration_blocking_reasons


class HelperSession:
    """Controller facade used by GUI and CLI code."""

    def __init__(self, *, dry_run: bool = False, fake_system: str | None = None) -> None:
        self.dry_run = dry_run
        self.fake_system = fake_system or os.environ.get("UHW_FAKE_SYSTEM")
        self._proc: subprocess.Popen | None = None
        self._rid = 0
        self._last_profile: SystemProfile | None = None
        self._last_plan: ModificationPlan | None = None
        self._last_verify: dict | None = None

    # ------------------------------------------------ legacy persistent transport
    def _ensure(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        self._proc = subprocess.Popen(
            ["pkexec", HELPER_PATH], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1)

    def request(self, cmd: str, args: dict | None = None, on_progress: ProgressCB | None = None) -> dict:
        """Send a legacy helper command.

        Kept for rollback/verification compatibility.  v0.42 apply uses the new
        one-shot apply-plan protocol below.
        """
        self._ensure()
        self._rid += 1
        assert self._proc and self._proc.stdin and self._proc.stdout
        self._proc.stdin.write(json.dumps({"request_id": self._rid, "cmd": cmd, "args": args or {}}) + "\n")
        self._proc.stdin.flush()
        while True:
            line = self._proc.stdout.readline()
            if not line:
                return {"success": False, "error_code": "HELPER_DIED", "message": "helper exited (authentication cancelled? pkexec needs a polkit agent)"}
            msg = json.loads(line)
            if msg.get("event") == "progress":
                if on_progress:
                    on_progress(msg.get("percent", 0), msg.get("line", ""))
                continue
            return msg

    # ------------------------------------------------ detection / planning
    def detect(self) -> DetectInfo:
        if self.fake_system:
            profile = load_fake_system(self.fake_system)
        else:
            # Normal System Check must stay unprivileged and must not trigger a
            # polkit prompt.  The helper repeats validation before real apply.
            profile = profile_from_probe_data(probe_current_system())
        self._last_profile = profile
        return self._detect_info_from_profile(profile)

    def _detect_info_from_profile(self, profile: SystemProfile) -> DetectInfo:
        secure_boot_on = "enabled" in (profile.secure_boot or "").lower()
        rows: list[tuple[str, str, str, str]] = []

        def row(title: str, detail: str, ok: bool, status_ok: str = "OK", status_bad: str = "Blocked") -> None:
            rows.append((title, detail, "success" if ok else "error", status_ok if ok else status_bad))

        row("Kernel hibernate support", "'disk' must be present in /sys/power/state", profile.has_hibernate_kernel_support, "Detected", "Missing")
        row("Bootloader", "v0.42 supports GRUB only", profile.bootloader == "grub", "GRUB", profile.bootloader or "Unsupported")
        row("Initramfs", "v0.42 supports initramfs-tools only", profile.initramfs == "initramfs-tools", "initramfs-tools", profile.initramfs or "Unsupported")
        rows.append(("Secure Boot", profile.secure_boot or "unknown", "warning" if secure_boot_on else "success", "Enabled" if secure_boot_on else "Disabled/unknown"))
        rows.append(("RAM", f"Detected RAM: {format_bytes_gib(profile.ram_bytes)}", "success", format_bytes_gib(profile.ram_bytes)))
        if profile.candidates:
            for cand in profile.candidates:
                cls = "success" if cand.selectable else "warning" if cand.status == "warning_option" else "error"
                status = cand.status.replace("_", " ").title()
                detail = cand.detail
                if cand.reasons:
                    detail += " — " + "; ".join(cand.reasons)
                if cand.warnings:
                    detail += " — " + "; ".join(cand.warnings)
                rows.append((cand.title, detail, cls, status))
        else:
            rows.append(("Disk swap target", "No active swap partition/file was detected. Use Configuration to create/resize /swap.img, or enable an existing swap target.", "warning", "Missing"))
        if profile.timeshift_available:
            rows.append(("Timeshift", "Optional snapshot tool detected", "success", "Available"))
        else:
            rows.append(("Timeshift", "Optional. File backup rollback remains available.", "warning", "Not installed"))

        blockers = profile.blocking_reasons
        return DetectInfo(
            rows=rows,
            secure_boot=secure_boot_on,
            ram_bytes=profile.ram_bytes,
            hard_stop=bool(blockers),
            profile=profile,
            candidates=profile.candidates,
        )

    def build_plan(self, selected_target: SwapTarget | str | SwapFileRequest | dict | None = None) -> ModificationPlan:
        if self._last_profile is None:
            self.detect()
        assert self._last_profile is not None
        if isinstance(selected_target, SwapFileRequest):
            plan = build_swapfile_modification_plan(self._last_profile, selected_target)
        elif isinstance(selected_target, dict) and selected_target.get("mode") == "create_or_resize":
            plan = build_swapfile_modification_plan(self._last_profile, SwapFileRequest.from_dict(selected_target))
        else:
            target = self._resolve_target(selected_target)
            plan = build_modification_plan(self._last_profile, target)
        self._last_plan = plan
        return plan

    def _resolve_target(self, selected_target: SwapTarget | str | None = None) -> SwapTarget:
        assert self._last_profile is not None
        if isinstance(selected_target, SwapTarget):
            return selected_target
        if isinstance(selected_target, str):
            for cand in self._last_profile.candidates:
                if cand.id == selected_target or cand.path == selected_target:
                    return cand
            raise ValueError("selected swap target was not found")
        target = self._last_profile.recommended_target
        if target is None:
            raise ValueError("no valid hibernation target is available")
        return target

    # ------------------------------------------------ apply
    def apply(self, selected_target: SwapTarget | str | SwapFileRequest | dict | None, on_progress: ProgressCB, *, dry_run: bool | None = None) -> tuple[bool, str]:
        plan = self.build_plan(selected_target)
        dry_run = self.dry_run if dry_run is None else dry_run
        if not plan.can_apply:
            return False, "; ".join(plan.blocking_reasons) or "plan is blocked"
        if dry_run or self.fake_system:
            return self._simulate_apply(plan, on_progress)
        return self._run_apply_helper(plan, on_progress)

    def _simulate_apply(self, plan: ModificationPlan, on_progress: ProgressCB) -> tuple[bool, str]:
        on_progress(1, "Dry-run mode: no system files will be written and no commands will be executed")
        if plan.swap_file_request is not None:
            on_progress(5, f"Managed swap-file request: {plan.swap_file_request.path} to {format_bytes_gib(plan.swap_file_request.size_bytes)}")
        else:
            on_progress(5, "Selected swap target: " + plan.selected_target.path)
        on_progress(8, "Backups for changed system files will be written to " + BACKUP_DIR_BASE + "/<backup_id>/manifest.json during real apply")
        on_progress(12, "Allowed managed files: " + ", ".join(plan.planned_files))
        for index, step in enumerate(plan.steps, start=1):
            pct = 15 + int(index * 75 / max(1, len(plan.steps)))
            on_progress(pct, f"Dry-run step {index}/{len(plan.steps)}: {step.title} — {step.detail}")
            time.sleep(0.02)
        on_progress(100, "Dry-run completed. Real apply would require authentication and a manual reboot afterward.")
        return True, "dry-run completed"

    def _run_apply_helper(self, plan: ModificationPlan, on_progress: ProgressCB) -> tuple[bool, str]:
        request = plan.to_helper_request(dry_run=False)
        proc = subprocess.Popen(
            ["pkexec", HELPER_PATH, "--action", "apply-plan", "--stdin-json"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1)
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.close()
        last_error = ""
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = event.get("message") or event.get("event", "")
            progress = event.get("progress")
            if isinstance(progress, (int, float)):
                on_progress(float(progress) * 100 if progress <= 1 else progress, msg)
            else:
                on_progress(0, msg)
            if event.get("event") == "error":
                last_error = msg
        stderr = proc.stderr.read() if proc.stderr else ""
        code = proc.wait()
        if code == 0:
            return True, "apply completed - reboot manually"
        return False, last_error or stderr.strip() or "helper apply failed"

    # ------------------------------------------------ rollback / verify compatibility
    def list_rollbacks(self) -> list[dict]:
        r = self.request("list-rollbacks")
        if not r.get("success"):
            raise RuntimeError(r.get("message") or r.get("error_code") or "list-rollbacks failed")
        return r.get("data", {}).get("snapshots", [])

    def preview_rollback(self, backup_id: str) -> dict:
        r = self.request("preview-rollback", {"backup_id": backup_id})
        if not r.get("success"):
            raise RuntimeError(r.get("message") or r.get("error_code") or "preview-rollback failed")
        return r.get("data", {})

    def rollback(self, backup_id: str, on_progress: ProgressCB | None = None) -> tuple[bool, str]:
        request = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": f"rollback-{int(time.time())}",
            "action": "rollback-files",
            "backup_id": backup_id,
            "dry_run": False,
        }
        proc = subprocess.Popen(
            ["pkexec", HELPER_PATH, "--action", "rollback-files", "--stdin-json"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1)
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.close()
        last_error = ""
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = event.get("message") or event.get("event", "")
            progress = event.get("progress")
            if on_progress:
                on_progress(float(progress) * 100 if isinstance(progress, (int, float)) and progress <= 1 else progress or 0, msg)
            if event.get("event") == "error":
                last_error = msg
        stderr = proc.stderr.read() if proc.stderr else ""
        code = proc.wait()
        return (code == 0, "rollback completed" if code == 0 else last_error or stderr.strip() or "rollback failed")

    def export_diagnostics(self) -> str:
        if self._last_profile is None:
            self.detect()
        assert self._last_profile is not None
        out_dir = Path.home() / ".cache" / "ubuntu-hibernate-wizard"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / ("ubuntu-hibernate-wizard-diagnostics-" + time.strftime("%Y%m%d-%H%M%S") + ".zip")
        write_diagnostic_zip(path, self._last_profile, self._last_plan, self._last_verify)
        return str(path)

    def verify(self, selected_target: SwapTarget | str | None = None) -> dict:
        if self.fake_system:
            if self._last_profile is None:
                self.detect()
            target = self._resolve_target(selected_target)
            ok = target.selectable
            return {"all_ok": ok, "errors": [] if ok else target.reasons, "checks": {"swap": ok, "uuid": ok, "offset": ok, "initramfs": ok}}
        if self._last_profile is None:
            self.detect()
        target = self._resolve_target(selected_target)
        r = self.request("verify", {"target": target.to_dict()})
        if not r.get("success"):
            raise RuntimeError(r.get("message") or r.get("error_code") or "verify failed")
        self._last_verify = r["data"]
        return r["data"]

    def repair(self) -> tuple[bool, str]:
        return False, "Repair is not implemented in v0.42; use Review & Apply with a valid target after resolving conflicts."

    def close(self) -> None:
        if self._proc and self._proc.poll() is None and self._proc.stdin:
            self._proc.stdin.close()
