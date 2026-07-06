"""CLI mode.

Verification remains read-only and in-process.  Rollback commands deliberately use
the same pkexec privileged-helper protocol as the GUI; the CLI never performs
root restore logic directly.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from ubuntu_hibernate_wizard.core import parsers, system

EXIT_OK, EXIT_MISMATCH, EXIT_CANNOT_CHECK = 0, 2, 3


def verify_json() -> int:
    """Emit read-only hibernation verification JSON.

    This uses the same v0.42 probe/classifier path as the GUI instead of
    hand-parsing swap offsets.  That keeps ext4/btrfs/encrypted-swap policy in
    one place and avoids the old filefrag fallback for btrfs swap files.
    """
    from ubuntu_hibernate_wizard.services.system_probe import probe_current_system, profile_from_probe_data

    result: dict = {"schema_version": 1}
    try:
        profile = profile_from_probe_data(probe_current_system())
        target = profile.recommended_target
        result.update({
            "bootloader": profile.bootloader,
            "initramfs": profile.initramfs,
            "kernel_hibernate_support": profile.has_hibernate_kernel_support,
            "blockers": profile.blocking_reasons,
        })
        if target is None:
            result.update(all_ok=False, errors=["no active disk swap partition/file usable for hibernation"] + profile.blocking_reasons)
            print(json.dumps(result, indent=2))
            return EXIT_MISMATCH
        result["swap_target"] = target.path
        result["target"] = target.to_dict()
        if not target.selectable:
            result.update(all_ok=False, errors=target.reasons or target.warnings or ["target is not selectable"])
            print(json.dumps(result, indent=2))
            return EXIT_MISMATCH
        active = [d.name for d in parsers.parse_swapon_show_bytes(profile.raw.get("swapon", ""))]
        vr = system.verify(
            target.path,
            active,
            target.uuid or "",
            target.resume_offset,
            profile.cmdline,
            profile.initramfs_resume,
            target_kind=target.kind,
        )
    except (parsers.ParseError, ValueError, OSError) as e:
        result.update(all_ok=False, errors=[f"verification error: {e}"])
        print(json.dumps(result, indent=2))
        return EXIT_MISMATCH

    result.update(
        all_ok=vr.all_ok,
        errors=vr.errors,
        fs_uuid=target.uuid,
        real_offset=target.resume_offset,
        checks={
            "swap": vr.active_swap_ok,
            "uuid": vr.resume_uuid_ok,
            "offset": vr.resume_offset_ok,
            "initramfs": vr.initramfs_resume_ok,
        },
    )
    print(json.dumps(result, indent=2))
    return EXIT_OK if vr.all_ok else EXIT_MISMATCH


def _session():
    from ubuntu_hibernate_wizard.backend.session import HelperSession
    return HelperSession()


def list_rollbacks_cli() -> int:
    try:
        snapshots = _session().list_rollbacks()
    except Exception as exc:  # noqa: BLE001
        print(f"Could not list rollbacks: {exc}", file=sys.stderr)
        print("pkexec requires a running polkit authentication agent; headless SSH sessions may need one.", file=sys.stderr)
        return EXIT_CANNOT_CHECK
    print(json.dumps({"snapshots": snapshots}, indent=2))
    return EXIT_OK


def _print_preview(data: dict) -> None:
    print(f"Rollback preview for {data.get('backup_id')}")
    if data.get("warning"):
        print(f"Warning: {data['warning']}")
    if not data.get("eligible", True):
        print("This snapshot is not eligible for rollback.")
        return
    for action in data.get("actions", []):
        path = f" {action.get('path')}" if action.get("path") else ""
        print(f"- {action.get('status')}: {action.get('type')}{path} - {action.get('reason') or ''}")


def preview_rollback_cli(backup_id: str) -> int:
    try:
        data = _session().preview_rollback(backup_id)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not preview rollback: {exc}", file=sys.stderr)
        return EXIT_CANNOT_CHECK
    _print_preview(data)
    return EXIT_OK if data.get("eligible", True) else EXIT_MISMATCH


def rollback_cli(backup_id: str, yes: bool) -> int:
    s = _session()
    try:
        data = s.preview_rollback(backup_id)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not preview rollback: {exc}", file=sys.stderr)
        return EXIT_CANNOT_CHECK
    _print_preview(data)
    if not data.get("eligible", True):
        return EXIT_MISMATCH
    if not yes:
        answer = input("Type yes to execute this rollback: ")
        if answer != "yes":
            print("Rollback cancelled.")
            return EXIT_MISMATCH
    def prog(_pct, line):
        if line:
            print(line)
    ok, msg = s.rollback(backup_id, prog)
    print(msg)
    return EXIT_OK if ok else EXIT_MISMATCH


def guard_notify() -> int:
    """Session watcher: notify once per distinct drift."""
    from ubuntu_hibernate_wizard.state import state_manager as sm
    status = sm.load_guard_status()
    marker = os.path.join(sm.STATE_DIR, "last-notified-hash")
    last = None
    try:
        last = open(marker).read().strip()
    except FileNotFoundError:
        pass
    if not sm.should_notify(status, last):
        return 0
    subprocess.run(["notify-send", "-a", "Hibernate Wizard", "-i", "io.github.ami3go.UbuntuHibernateWizard",
                    "Hibernation configuration is out of date", "Open Hibernate Wizard to repair."], check=False)
    os.makedirs(sm.STATE_DIR, exist_ok=True)
    open(marker, "w").write(sm.status_hash(status))
    return 0



def _arg_value(argv: list[str], name: str) -> str | None:
    if name not in argv:
        return None
    try:
        return argv[argv.index(name) + 1]
    except IndexError:
        return None


def gate_e_cli(mode: str, argv: list[str]) -> int:
    """Run a Gate E validation phase for disposable Ubuntu VMs."""
    from ubuntu_hibernate_wizard.services.gate_e_validator import (
        GATE_E_ACK_TEXT,
        render_text_summary,
        run_gate_e,
        write_report,
    )
    ack = _arg_value(argv, "--gate-e-ack")
    report_dir = _arg_value(argv, "--gate-e-report-dir")
    report_path = _arg_value(argv, "--gate-e-report")
    allow_physical = "--gate-e-allow-physical" in argv
    report = run_gate_e(mode, ack=ack, allow_physical=allow_physical)
    path = write_report(report, report_dir=report_dir, report_path=report_path)
    print(render_text_summary(report, path))
    if report.status in {"passed", "manual_hibernate_pending"}:
        return EXIT_OK
    if mode == "apply" and ack != GATE_E_ACK_TEXT:
        print(f"\nTo run real apply in a disposable VM, pass: --gate-e-ack {GATE_E_ACK_TEXT}", file=sys.stderr)
    return EXIT_MISMATCH



def _bool_flag(argv: list[str], name: str) -> bool:
    return name in argv


def gate_f_record_manual_cli(argv: list[str]) -> int:
    """Create the manual hibernate/resume evidence record used by Gate F."""
    from ubuntu_hibernate_wizard.services.gate_f_release import (
        GateFError, create_manual_record, write_manual_record,
    )
    gate_e_report = _arg_value(argv, "--gate-e-report")
    output = _arg_value(argv, "--output") or _arg_value(argv, "--gate-f-manual-record")
    operator = _arg_value(argv, "--operator") or os.environ.get("USER") or ""
    manual_status = _arg_value(argv, "--manual-status") or "passed"
    notes = _arg_value(argv, "--notes") or ""
    if not gate_e_report or not output:
        print("--gate-f-record-manual requires --gate-e-report <path> and --output <path>", file=sys.stderr)
        return EXIT_CANNOT_CHECK
    try:
        record = create_manual_record(
            gate_e_report_path=gate_e_report,
            manual_status=manual_status,
            reboot_performed=_bool_flag(argv, "--reboot-performed"),
            hibernate_attempted=_bool_flag(argv, "--hibernate-attempted"),
            resumed_successfully=_bool_flag(argv, "--resumed-successfully"),
            post_resume_verify_passed=_bool_flag(argv, "--post-resume-verify-passed"),
            operator=operator,
            notes=notes,
        )
        path = write_manual_record(record, output)
    except GateFError as exc:
        print(f"Could not create Gate F manual record: {exc}", file=sys.stderr)
        return EXIT_MISMATCH
    print(f"Gate F manual record written: {path}")
    return EXIT_OK


def gate_f_check_cli(argv: list[str]) -> int:
    """Validate Gate E + manual evidence and produce a Gate F manifest."""
    from ubuntu_hibernate_wizard.services.gate_f_release import (
        GateFError, build_gate_f_manifest, render_gate_f_summary, write_gate_f_manifest,
    )
    gate_e_report = _arg_value(argv, "--gate-e-report")
    manual_record = _arg_value(argv, "--manual-record") or _arg_value(argv, "--gate-f-manual-record")
    output = _arg_value(argv, "--output") or _arg_value(argv, "--gate-f-manifest") or "dist/gate-f-manifest.json"
    if not gate_e_report or not manual_record:
        print("--gate-f-check requires --gate-e-report <path> and --manual-record <path>", file=sys.stderr)
        return EXIT_CANNOT_CHECK
    try:
        manifest = build_gate_f_manifest(gate_e_report, manual_record)
        path = write_gate_f_manifest(manifest, output)
    except GateFError as exc:
        print(f"Could not evaluate Gate F evidence: {exc}", file=sys.stderr)
        return EXIT_MISMATCH
    print(render_gate_f_summary(manifest, path))
    return EXIT_OK if manifest.status == "release_candidate_ready" else EXIT_MISMATCH

def main(argv: list[str]) -> int | None:
    """Returns exit code for CLI flags, None to launch the GUI."""
    if "--gate-f-record-manual" in argv:
        return gate_f_record_manual_cli(argv)
    if "--gate-f-check" in argv:
        return gate_f_check_cli(argv)
    if "--gate-e-preflight" in argv:
        return gate_e_cli("preflight", argv)
    if "--gate-e-validate-plan" in argv:
        return gate_e_cli("validate-plan", argv)
    if "--gate-e-dry-run" in argv:
        return gate_e_cli("dry-run", argv)
    if "--gate-e-apply" in argv:
        return gate_e_cli("apply", argv)
    if "--verify" in argv or "--check" in argv:
        return verify_json()
    if "--list-rollbacks" in argv:
        return list_rollbacks_cli()
    if "--preview-rollback" in argv:
        try:
            return preview_rollback_cli(argv[argv.index("--preview-rollback") + 1])
        except IndexError:
            print("--preview-rollback requires a backup_id", file=sys.stderr)
            return EXIT_CANNOT_CHECK
    if "--rollback" in argv:
        try:
            backup_id = argv[argv.index("--rollback") + 1]
        except IndexError:
            print("--rollback requires a backup_id", file=sys.stderr)
            return EXIT_CANNOT_CHECK
        return rollback_cli(backup_id, "--yes" in argv)
    if "--guard-check" in argv:
        return guard_check()
    if "--guard-notify" in argv:
        return guard_notify()
    return None


def guard_check() -> int:
    """Root guard: verify read-only, write status file, never modify."""
    import datetime
    import io
    from contextlib import redirect_stdout
    from ubuntu_hibernate_wizard.state import state_manager as sm
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = verify_json()
    try:
        data = json.loads(buf.getvalue())
    except json.JSONDecodeError:
        data = {"all_ok": False, "errors": ["guard: verify produced no JSON"]}
    sm.write_guard_status(bool(data.get("all_ok")), data.get("errors", []), datetime.datetime.now().isoformat())
    return 0 if code == EXIT_OK else code
