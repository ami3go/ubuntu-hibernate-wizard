#!/usr/bin/env python3
"""Persistent privileged helper for Ubuntu Hibernate Wizard.

Protocol: newline-delimited JSON on stdin/stdout.
  request : {"request_id": N, "cmd": "...", "args": {...}}
  progress: {"request_id": N, "event": "progress", "percent": P, "line": "..."}
  response: {"request_id": N, "success": bool, "changed": bool,
             "error_code": str|null, "message": str, "stdout": str,
             "stderr": str, "reboot_required": bool, "data": {...}}

All system mutations are guarded by an approved exact-argument plan.  Rollback
snapshots are helper-owned and manifest-backed.

v0.42 managed files: /etc/initramfs-tools/conf.d/resume and
/etc/default/grub.d/hibernate-wizard.cfg.
"""
from __future__ import annotations

import fcntl
import json
import os
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ubuntu_hibernate_wizard.constants import (  # noqa: E402
    APP_VERSION, GRUB_FRAGMENT, HELPER_EXECUTABLE, MANAGED_FILES,
    PROTOCOL_VERSION, RESUME_FILE,
)
from ubuntu_hibernate_wizard.core import parsers, system  # noqa: E402
from ubuntu_hibernate_wizard.core import rollback as rb  # noqa: E402
from ubuntu_hibernate_wizard.services.hibernate_planner import (  # noqa: E402
    FSTAB_FILE, GIB, MIN_ROOT_FREE_AFTER_SWAPFILE_BYTES, SwapFileRequest, build_modification_plan,
    generated_grub_fragment, generated_resume_config,
)
from ubuntu_hibernate_wizard.services.system_probe import (  # noqa: E402
    probe_current_system, profile_from_probe_data,
)
from ubuntu_hibernate_wizard.services.swap_target_model import SwapTarget  # noqa: E402

HELPER_LOCK_PATH = "/run/ubuntu-hibernate-wizard/helper.lock"
IDLE_TIMEOUT = 15 * 60
ENV = {"LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}

# Public JSONL mutation surface is intentionally tiny.  The v0.42+ public
# apply flow uses the one-shot apply-plan protocol at the bottom of this file.
# Legacy begin/finish/update-grub/update-initramfs/cleanup commands remain as
# private dead-code-compatible methods for old manifests/tests, but they are no
# longer accepted by the persistent helper protocol.  This prevents stale GUI or
# third-party callers from bypassing the live one-shot target validation path.
DISABLED_LEGACY_MUTATING = {
    "begin-operation", "finish-operation", "mark-operation-failed",
    "update-grub-resume", "update-initramfs-resume", "cleanup-old-swap-backup",
}
MUTATING = {"rollback"}

READ_ONLY = {"detect", "verify", "list-rollbacks", "preview-rollback", "submit-plan", "helper-version"}


def run(argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a fixed argv list.  Never pass shell strings from the manifest."""
    return subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout, env=ENV)


class Helper:
    def __init__(self) -> None:
        self.plan: dict | None = None
        self.plan_commands: dict[str, dict] = {}
        self.consumed_commands: set[str] = set()
        self.active_backup_id: str | None = None
        self.active_operation: str | None = None
        self.backup_manager: rb.BackupManager | None = None
        self._operation_lock_file = None

    # ---------------------------------------------------------------- read-only
    def cmd_detect(self, args: dict) -> dict:
        """Read-only system probe for v0.42.

        The helper uses the same probing implementation as the unprivileged GUI,
        but runs it as root when invoked for helper-side validation.
        """
        return {"success": True, "data": probe_current_system()}

    def cmd_verify(self, args: dict) -> dict:
        """Verify selected target against kernel cmdline/initramfs config.

        Accepts either v0.42 {target: {...}} or legacy {swap_file: "/swap.img"}.
        """
        if "target" in args:
            target = SwapTarget.from_dict(args["target"])
        else:
            swap = self._valid_swap_path(args["swap_file"])
            out = run(["findmnt", "-no", "SOURCE,FSTYPE,UUID", "-T", swap])
            _, fstype, uuid = parsers.parse_findmnt_target(out.stdout)
            if fstype != "ext4":
                return {"success": False, "error_code": "UNSUPPORTED_FS", "message": f"swap file is on {fstype}, ext4 required"}
            offset = parsers.parse_filefrag_offset(run(["filefrag", "-v", swap]).stdout)
            target = SwapTarget(id=swap, kind="file", path=swap, size_bytes=0,
                                uuid=uuid, filesystem=fstype, resume_offset=offset,
                                status="valid_option")
        active = [d.name for d in parsers.parse_swapon_show_bytes(run(["swapon", "--show", "--bytes"]).stdout)]
        initrd = self._read(RESUME_FILE)
        result = system.verify(target.path, active, target.uuid or "", target.resume_offset,
                               self._read("/proc/cmdline"), initrd,
                               target_kind=target.kind)
        return {"success": True, "data": {
            "all_ok": result.all_ok, "errors": result.errors,
            "real_offset": target.resume_offset, "fs_uuid": target.uuid,
            "checks": {"swap": result.active_swap_ok,
                       "uuid": result.resume_uuid_ok,
                       "offset": result.resume_offset_ok,
                       "initramfs": result.initramfs_resume_ok}}}

    def cmd_helper_version(self, args: dict) -> dict:
        return {"success": True, "data": {"helper": HELPER_EXECUTABLE, "app_version": APP_VERSION, "protocol_version": PROTOCOL_VERSION}}

    def cmd_list_rollbacks(self, args: dict) -> dict:
        return {"success": True, "data": {"snapshots": rb.list_snapshots(active_backup_id=self.active_backup_id)}}

    def cmd_preview_rollback(self, args: dict) -> dict:
        backup_id = rb.validate_backup_id(args["backup_id"])
        manifest = rb.validate_manifest_security(backup_id)
        if manifest.status == "rolled-back":
            eligible = False
            warning = "ROLLBACK_NOT_ELIGIBLE"
        else:
            eligible = manifest.status in rb.ROLLBACK_ELIGIBLE_STATUSES or manifest.status in {"in-progress", "rollback-in-progress"}
            warning = "retrying rollback" if manifest.status in {"rolled-back-partial", "rollback-failed"} else None
        actions = [a.asdict() for a in rb.RollbackPlanner().build_plan(manifest)] if eligible else []
        return {"success": True, "data": {"backup_id": backup_id, "eligible": eligible, "warning": warning, "actions": actions}}

    # -------------------------------------------------------------- plan gating
    def cmd_submit_plan(self, args: dict) -> dict:
        plan = args["plan"]
        rb.reject_placeholder_values(plan)
        if not isinstance(plan, dict):
            raise ValueError("BAD_PLAN")
        if plan.get("schema_version") != 1:
            raise ValueError("BAD_PLAN_SCHEMA")
        commands = plan.get("commands", {})
        if not isinstance(commands, dict):
            raise ValueError("BAD_PLAN")
        for cmd, approved in commands.items():
            if cmd not in MUTATING:
                raise ValueError(f"BAD_PLAN_COMMAND:{cmd}")
            if approved is True:
                raise ValueError("BOOLEAN_PLAN_NOT_ALLOWED")
            if not isinstance(approved, dict):
                raise ValueError("BAD_PLAN_ARGS")
            if "backup_id" in approved and cmd not in {"rollback", "cleanup-old-swap-backup"}:
                raise ValueError("BACKUP_ID_NOT_ALLOWED_IN_OPERATION_PLAN")
            if "backup_id" in approved and isinstance(approved["backup_id"], dict):
                raise ValueError("BACKUP_ID_WILDCARD_NOT_ALLOWED")
        self.plan = plan
        # Replacing a plan must not reopen commands already consumed in this active operation.
        self.plan_commands = commands
        return {"success": True, "message": "plan registered"}

    def _require_plan(self, cmd: str, args: dict) -> None:
        if not self.plan_commands or cmd not in self.plan_commands:
            raise PermissionError("NOT_IN_PLAN")
        if cmd in self.consumed_commands and cmd not in {"mark-operation-failed", "finish-operation"}:
            raise PermissionError("NOT_IN_PLAN")

        approved = self.plan_commands[cmd]
        compare_args = dict(args)

        if cmd == "begin-operation":
            if args.get("operation") == "rollback-safety-snapshot":
                raise PermissionError("NOT_IN_PLAN")
            if self.active_backup_id is not None:
                raise RuntimeError("E_OPERATION_ACTIVE")
        elif cmd == "rollback":
            # Rollback is a separate operation; its backup_id is exact-plan matched.
            rb.validate_backup_id(args.get("backup_id"))
        elif cmd == "cleanup-old-swap-backup":
            rb.validate_backup_id(args.get("backup_id"))
        else:
            if not self.active_backup_id:
                raise PermissionError("NO_ACTIVE_OPERATION")
            if args.get("backup_id") != self.active_backup_id:
                raise PermissionError("NOT_IN_PLAN")
            compare_args.pop("backup_id", None)
            if cmd == "mark-operation-failed":
                # Failure metadata is not knowable before the operation starts;
                # backup_id is still bound to the active operation context.
                compare_args = {}

        self._compare_exact_args(cmd, approved, compare_args)

        if "swap_file" in args:
            self._valid_swap_path(args["swap_file"])
        if "uuid" in args:
            parsers.validate_uuid(args["uuid"])
        if "offset" in args and (not isinstance(args["offset"], int) or args["offset"] <= 0):
            raise ValueError("invalid offset")
        self.consumed_commands.add(cmd)

    @staticmethod
    def _compare_exact_args(cmd: str, approved: dict, runtime: dict) -> None:
        if set(approved.keys()) != set(runtime.keys()):
            raise PermissionError("NOT_IN_PLAN")
        for key, expected in approved.items():
            actual = runtime[key]
            if isinstance(expected, dict) and set(expected.keys()) == {"any_of"}:
                if not (cmd == "finish-operation" and key == "status"):
                    raise PermissionError("NOT_IN_PLAN")
                if actual not in expected["any_of"]:
                    raise PermissionError("NOT_IN_PLAN")
            elif actual != expected:
                raise PermissionError("NOT_IN_PLAN")

    def _invalidate_plan(self) -> None:
        self.plan = None
        self.plan_commands = {}
        self.consumed_commands.clear()

    # ------------------------------------------------------------- operations
    def cmd_begin_operation(self, args: dict, emit) -> dict:
        operation = args["operation"]
        if operation == "rollback-safety-snapshot":
            return {"success": False, "error_code": "NOT_IN_PLAN", "message": "reserved helper-internal operation"}
        self._acquire_operation_lock()
        try:
            bm = rb.BackupManager.begin(operation)
            self.active_backup_id = bm.backup_id
            self.active_operation = operation
            self.backup_manager = bm
            emit(2, f"Rollback snapshot created: {bm.snapshot}")
            return {"success": True, "changed": True, "data": {"backup_id": bm.backup_id, "backup_dir": str(bm.snapshot)}}
        except Exception:
            self._release_operation_lock()
            raise

    def cmd_finish_operation(self, args: dict, emit) -> dict:
        backup_id = rb.validate_backup_id(args["backup_id"])
        if backup_id != self.active_backup_id:
            return {"success": False, "error_code": "NO_ACTIVE_OPERATION", "message": "backup_id is not active"}
        status = args["status"]
        if status not in {"completed", "failed"}:
            return {"success": False, "error_code": "BAD_STATUS"}
        bm = self._active_backup(backup_id)
        bm.mark_status(status)
        emit(100, f"operation manifest marked {status}")
        self.active_backup_id = None
        self.active_operation = None
        self.backup_manager = None
        self._release_operation_lock()
        self._invalidate_plan()
        return {"success": True, "changed": True}

    def cmd_mark_operation_failed(self, args: dict, emit) -> dict:
        backup_id = rb.validate_backup_id(args["backup_id"])
        if backup_id != self.active_backup_id:
            return {"success": False, "error_code": "NO_ACTIVE_OPERATION", "message": "backup_id is not active"}
        bm = self._active_backup(backup_id)
        bm.mark_status("failed", failed_step=args.get("failed_step"), error_code=args.get("error_code"), message=args.get("message"))
        emit(100, f"operation marked failed at {args.get('failed_step', 'unknown step')}")
        return {"success": True, "changed": True}

    # ------------------------------------------------------------- mutations

    def cmd_update_grub_resume(self, args: dict, emit) -> dict:
        """Write v0.42 managed GRUB fragment instead of rewriting /etc/default/grub."""
        backup_id = args["backup_id"]
        target = SwapTarget(
            id=args.get("path", args.get("swap_file", "selected")),
            kind=args.get("kind", "file" if args.get("offset") else "partition"),
            path=args.get("path", args.get("swap_file", "selected")),
            size_bytes=0,
            uuid=args["uuid"],
            resume_offset=args.get("offset"),
            status="valid_option",
        )
        content = generated_grub_fragment(target)
        emit(5, f"writing managed GRUB fragment: {GRUB_FRAGMENT}")
        emit(10, f"target kernel parameters: resume=UUID={args['uuid']}" + (f" resume_offset={args.get('offset')}" if args.get("offset") else ""))
        original = self._read(GRUB_FRAGMENT)
        if original != content:
            self._atomic_write(GRUB_FRAGMENT, content.encode("utf-8"), backup_id=backup_id, managed_by_wizard=True, emit=emit)
        else:
            emit(25, f"{GRUB_FRAGMENT} already contains the requested managed fragment")
        emit(50, "running command: update-grub")
        r = run(["update-grub"], timeout=180)
        if r.returncode != 0 and shutil.which("grub-mkconfig"):
            emit(65, "update-grub failed or is unavailable; trying verified fallback: grub-mkconfig -o /boot/grub/grub.cfg")
            r = run(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"], timeout=180)
        if r.stdout.strip():
            emit(70, "GRUB command stdout captured; first line: " + r.stdout.strip().splitlines()[0][:180])
        if r.returncode != 0:
            if r.stderr.strip():
                emit(100, "GRUB command stderr: " + r.stderr.strip().splitlines()[0][:180])
            return {"success": False, "error_code": "UPDATE_GRUB_FAILED", "message": "GRUB regeneration returned non-zero exit status", "stdout": r.stdout, "stderr": r.stderr}
        emit(100, "GRUB regeneration completed successfully")
        return {"success": True, "changed": original != content, "reboot_required": True, "stdout": r.stdout}

    def cmd_update_initramfs_resume(self, args: dict, emit) -> dict:
        backup_id = args["backup_id"]
        target = SwapTarget(
            id=args.get("path", args.get("swap_file", "selected")),
            kind=args.get("kind", "file" if args.get("offset") else "partition"),
            path=args.get("path", args.get("swap_file", "selected")),
            size_bytes=0,
            uuid=args["uuid"],
            resume_offset=args.get("offset"),
            status="valid_option",
        )
        content = generated_resume_config(target)
        emit(5, f"writing {RESUME_FILE}")
        emit(10, "new file content: " + content.strip())
        original = self._read(RESUME_FILE)
        if original != content:
            self._atomic_write(RESUME_FILE, content.encode("utf-8"), backup_id=backup_id, managed_by_wizard=True, emit=emit)
        else:
            emit(15, f"{RESUME_FILE} already contains the requested content; file write skipped")
        emit(30, "running command: update-initramfs -u")
        r = run(["update-initramfs", "-u"], timeout=900)
        if r.stdout.strip():
            emit(70, "update-initramfs stdout captured; first line: " + r.stdout.strip().splitlines()[0][:180])
        if r.returncode != 0:
            if r.stderr.strip():
                emit(100, "update-initramfs stderr: " + r.stderr.strip().splitlines()[0][:180])
            return {"success": False, "error_code": "UPDATE_INITRAMFS_FAILED", "message": "update-initramfs failed", "stdout": r.stdout, "stderr": r.stderr}
        emit(100, "update-initramfs completed successfully")
        return {"success": True, "changed": original != content, "reboot_required": True}




    def cmd_rollback(self, args: dict, emit) -> dict:
        backup_id = rb.validate_backup_id(args["backup_id"])
        mode = args.get("mode", "safe")
        if mode != "safe":
            return {"success": False, "error_code": "UNSUPPORTED_ROLLBACK_MODE"}
        if self.active_backup_id is not None:
            return {"success": False, "error_code": "E_OPERATION_ACTIVE"}
        self._acquire_operation_lock()
        meaningful_success = False
        failures: list[dict] = []
        regeneration_failed = False
        changed_reboot_sensitive = False
        try:
            emit(2, f"Rollback: loading manifest {backup_id}")
            manifest = rb.validate_manifest_security(backup_id)
            stale_rollback_in_progress = manifest.status == "rollback-in-progress" and self.active_backup_id is None
            if manifest.status not in rb.ROLLBACK_ELIGIBLE_STATUSES and not stale_rollback_in_progress:
                return {"success": False, "error_code": "ROLLBACK_NOT_ELIGIBLE", "message": f"status {manifest.status} cannot be rolled back"}
            original_status = manifest.status
            bm = rb.BackupManager(backup_id)
            bm.mark_status("rollback-in-progress")
            emit(5, "Rollback: validating snapshot ownership and paths")
            emit(8, "Rollback: creating pre-rollback safety snapshot")
            try:
                rb.BackupManager.begin("rollback-safety-snapshot")
            except Exception as exc:  # noqa: BLE001
                bm.mark_status(original_status)
                return {"success": False, "error_code": "SAFETY_SNAPSHOT_FAILED", "message": str(exc)}
            actions = rb.RollbackPlanner().build_plan(bm.reload())
            executed: list[dict] = []
            for action in actions:
                if action.status != "will-run":
                    executed.append(action.asdict())
                    emit(20, f"Rollback: skipping {action.type} {action.path or ''}: {action.reason}")
                    continue
                emit(30, f"Rollback: {action.type} {action.path or ''}".rstrip())
                ok, reason = self._execute_rollback_action(bm, action)
                item = action.asdict()
                item["executed"] = True
                item["success"] = ok
                if reason:
                    item["result_reason"] = reason
                executed.append(item)
                if ok:
                    meaningful_success = True
                    if action.path in {"/etc/default/grub", "/etc/fstab", "/etc/initramfs-tools/conf.d/resume", "/etc/systemd/sleep.conf.d/99-ubuntu-hibernate-wizard.conf", "/etc/polkit-1/rules.d/49-ubuntu-hibernate-wizard.rules"}:
                        changed_reboot_sensitive = True
                else:
                    failures.append(item)
                    if action.type in {"rerun-update-grub", "rerun-update-initramfs"}:
                        regeneration_failed = True
            if failures:
                status = "rolled-back-partial" if meaningful_success else "rollback-failed"
            else:
                status = "rolled-back"
            if regeneration_failed:
                status = "rolled-back-partial"
                executed.append({"type": "warning", "reason": "REGENERATION_FAILED_DO_NOT_REBOOT", "success": False})
            bm.mark_status(status, rollback_results=executed)
            reboot_required = bool(changed_reboot_sensitive and not regeneration_failed and status == "rolled-back")
            if status == "rolled-back":
                msg = "Rollback completed - reboot recommended" if reboot_required else "Rollback completed"
            elif status == "rolled-back-partial":
                msg = "Rollback partially completed - review skipped/failed actions before reboot"
            else:
                msg = "Rollback failed before a safe restore could complete"
            emit(100, msg)
            return {"success": status in {"rolled-back", "rolled-back-partial"}, "changed": meaningful_success, "message": msg, "reboot_required": reboot_required, "data": {"status": status, "actions": executed}}
        finally:
            self._release_operation_lock()
            self._invalidate_plan()

    def cmd_cleanup_old_swap_backup(self, args: dict, emit) -> dict:
        backup_id = rb.validate_backup_id(args["backup_id"])
        manifest = rb.validate_manifest_security(backup_id)
        swap = manifest.swap or {}
        removed: list[str] = []
        for kind, key in (("old", "old_swap_backup_name"), ("current", "rollback_current_name"), ("side", "side_file_name")):
            try:
                p = rb.validate_swap_sibling(swap.get("path"), swap.get(key), backup_id, kind=kind)
            except Exception:
                continue
            if p and p.exists() and str(p) not in {"/swap.img", "/swapfile"}:
                p.unlink()
                removed.append(str(p))
        emit(100, f"cleanup removed {len(removed)} rollback swap file(s)")
        return {"success": True, "changed": bool(removed), "data": {"removed": removed}}

    # -------------------------------------------------------------- utilities
    @staticmethod
    def _valid_swap_path(p: str) -> str:
        return rb.validate_swap_path(p)

    @staticmethod
    def _read(path: str) -> str:
        try:
            return open(path).read()
        except FileNotFoundError:
            return ""

    def _active_backup(self, backup_id: str) -> rb.BackupManager:
        if backup_id != self.active_backup_id or self.backup_manager is None:
            raise RuntimeError("NO_ACTIVE_OPERATION")
        self.backup_manager.reload()
        return self.backup_manager

    def _atomic_write(self, path: str, content: bytes, *, backup_id: str, managed_by_wizard: bool, emit=None) -> None:
        bm = self._active_backup(backup_id)
        bm.record_before_write(path, managed_by_wizard=managed_by_wizard)
        if emit:
            emit(20, f"manifest recorded original state for {path}")
        rb.atomic_write_bytes(path, content, mode=0o644, uid=0, gid=0)
        bm.record_after_write(path)
        if emit:
            emit(35, f"atomic write complete and sha256_after recorded for {path}")


    @staticmethod
    def _is_swap_active(path: str) -> bool:
        active = [d.name for d in parsers.parse_swapon_show_bytes(run(["swapon", "--show", "--bytes"]).stdout)]
        return path in active

    def _execute_rollback_action(self, bm: rb.BackupManager, action: rb.RollbackAction) -> tuple[bool, str | None]:
        try:
            if action.type == "restore-file":
                manifest = bm.reload()
                mf = next(f for f in manifest.files if f.path == action.path)
                mode, uid, gid = rb.validate_metadata(mf.mode_before, mf.uid_before, mf.gid_before)
                backup_path = rb.snapshot_dir(manifest.backup_id) / (mf.backup or "")
                data = backup_path.read_bytes()
                rb.atomic_write_bytes(mf.path, data, mode=mode, uid=uid, gid=gid)
                return True, None
            if action.type == "remove-created-file":
                try:
                    os.unlink(action.path)
                except FileNotFoundError:
                    pass
                return True, None
            if action.type == "remove-created-empty-dir":
                try:
                    os.rmdir(action.path)
                except OSError as exc:
                    return False, str(exc)
                return True, None
            if action.type == "restore-old-swap-file":
                return self._rollback_restore_old_swap(bm)
            if action.type == "remove-wizard-created-swap":
                return self._rollback_remove_wizard_swap(bm)
            if action.type == "cleanup-side-swap-file":
                manifest = bm.reload()
                p = rb.validate_swap_sibling(manifest.swap["path"], manifest.swap.get("side_file_name"), manifest.backup_id, kind="side")
                if p and p.exists():
                    p.unlink()
                bm.set_swap_side_file(None)
                return True, None
            if action.type == "rerun-update-grub":
                r = run(["update-grub"], timeout=180)
                return r.returncode == 0, r.stderr.strip() or r.stdout.strip() or None
            if action.type == "rerun-update-initramfs":
                r = run(["update-initramfs", "-u", "-k", "all"], timeout=900)
                return r.returncode == 0, r.stderr.strip() or r.stdout.strip() or None
            if action.type == "reload-systemd-daemon":
                r = run(["systemctl", "daemon-reload"], timeout=60)
                return r.returncode == 0, r.stderr.strip() or r.stdout.strip() or None
            return False, "UNKNOWN_ROLLBACK_ACTION"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _rollback_restore_old_swap(self, bm: rb.BackupManager) -> tuple[bool, str | None]:
        manifest = bm.reload()
        swap = manifest.swap or {}
        path = rb.validate_swap_path(swap.get("path"))
        old = rb.validate_swap_sibling(path, swap.get("old_swap_backup_name"), manifest.backup_id, kind="old")
        if not old or not old.exists():
            return False, "OLD_SWAP_BACKUP_MISSING"
        if self._is_swap_active(path):
            r = run(["swapoff", path])
            if r.returncode != 0:
                return False, "SWAPOFF_FAILED_SWAP_NOT_ROLLED_BACK"
        current_name = rb.expected_rollback_current_name(path, manifest.backup_id)
        current = Path(path).with_name(current_name)
        if Path(path).exists():
            os.replace(path, current)
            os.chmod(current, 0o600)
            bm.set_rollback_current_name(current_name)
        os.replace(old, path)
        os.chmod(path, 0o600)
        if swap.get("was_active_before"):
            r = run(["swapon", path])
            if r.returncode != 0:
                return False, "RESTORED_SWAP_SWAPON_FAILED"
        return True, None

    def _rollback_remove_wizard_swap(self, bm: rb.BackupManager) -> tuple[bool, str | None]:
        manifest = bm.reload()
        swap = manifest.swap or {}
        path = rb.validate_swap_path(swap.get("path"))
        if swap.get("existed_before") is not False:
            return False, "PREEXISTING_SWAP_NOT_DELETED"
        if self._is_swap_active(path):
            r = run(["swapoff", path])
            if r.returncode != 0:
                return False, "SWAPOFF_FAILED_SWAP_NOT_ROLLED_BACK"
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        return True, None

    def _acquire_operation_lock(self) -> None:
        if self._operation_lock_file is not None:
            raise RuntimeError("E_OPERATION_ACTIVE")
        Path(HELPER_LOCK_PATH).parent.mkdir(parents=True, exist_ok=True)
        lock_file = open(HELPER_LOCK_PATH, "w")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.close()
            raise RuntimeError("E_OPERATION_ACTIVE") from exc
        self._operation_lock_file = lock_file

    def _release_operation_lock(self) -> None:
        if self._operation_lock_file is None:
            return
        try:
            fcntl.flock(self._operation_lock_file, fcntl.LOCK_UN)
            self._operation_lock_file.close()
        finally:
            self._operation_lock_file = None

    # ------------------------------------------------------------- session loop
    def serve(self) -> int:
        last = time.time()
        try:
            while True:
                r, _, _ = select.select([sys.stdin], [], [], 30)
                if not r:
                    if time.time() - last > IDLE_TIMEOUT:
                        return 0
                    continue
                line = sys.stdin.readline()
                if not line:
                    return 0
                last = time.time()
                rid = 0
                try:
                    req = json.loads(line)
                    rid, cmd = req["request_id"], req["cmd"]
                    args = req.get("args", {})
                    emit = lambda p, msg, _rid=rid: print(json.dumps({"request_id": _rid, "event": "progress", "percent": p, "line": msg}), flush=True)
                    if cmd not in MUTATING and cmd not in READ_ONLY:
                        resp = {"success": False, "error_code": "UNKNOWN_CMD"}
                    else:
                        if cmd in MUTATING:
                            self._require_plan(cmd, args)
                        fn = getattr(self, "cmd_" + cmd.replace("-", "_"), None)
                        if fn is None:
                            resp = {"success": False, "error_code": "UNKNOWN_CMD"}
                        else:
                            resp = fn(args, emit) if cmd in MUTATING else fn(args)
                except PermissionError as exc:
                    code = str(exc) or "NOT_IN_PLAN"
                    resp = {"success": False, "error_code": code, "message": "operation not in the approved plan"}
                except RuntimeError as exc:
                    code = str(exc)
                    if code == "E_OPERATION_ACTIVE":
                        resp = {"success": False, "error_code": "E_OPERATION_ACTIVE", "message": "another privileged operation is active"}
                    else:
                        resp = {"success": False, "error_code": "INTERNAL", "message": code}
                except Exception as exc:  # noqa: BLE001
                    resp = {"success": False, "error_code": "INTERNAL", "message": str(exc)}
                resp.setdefault("changed", False)
                resp.setdefault("reboot_required", False)
                resp["request_id"] = rid
                print(json.dumps(resp), flush=True)
        finally:
            self._release_operation_lock()


# ---------------------------------------------------------------- one-shot v0.42 protocol
STEP_IDS = {
    "validate_target", "create_rollback", "ensure_swap_file",
    "write_resume_config", "write_grub_config", "update_initramfs", "update_grub",
}
ACTIONS = {"helper-version", "validate-plan", "apply-plan", "rollback-files"}


def _event(request_id: str, event: str, *, step_id: str | None = None,
           status: str | None = None, message: str = "", progress: float | None = None,
           **extra) -> None:
    from datetime import datetime, timezone
    msg = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "event": event,
        "message": message,
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    if step_id is not None:
        msg["step_id"] = step_id
    if status is not None:
        msg["status"] = status
    if progress is not None:
        msg["progress"] = progress
    msg.update(extra)
    print(json.dumps(msg), flush=True)


TOP_LEVEL_BY_ACTION = {
    "helper-version": {"protocol_version", "request_id", "action"},
    "validate-plan": {"protocol_version", "request_id", "action", "dry_run", "app_version", "selected_target", "swap_file_request", "rollback", "planned_files", "steps"},
    "apply-plan": {"protocol_version", "request_id", "action", "dry_run", "app_version", "selected_target", "swap_file_request", "rollback", "planned_files", "steps"},
    "rollback-files": {"protocol_version", "request_id", "action", "backup_id", "dry_run"},
}


def _reject_unknown_fields(req: dict, action: str) -> None:
    allowed = TOP_LEVEL_BY_ACTION[action]
    unknown = set(req) - allowed
    if unknown:
        raise ValueError("UNKNOWN_REQUEST_FIELDS:" + ",".join(sorted(unknown)))


def _validate_one_shot_request(req: dict) -> tuple[SwapTarget | None, SwapFileRequest | None]:
    if not isinstance(req, dict):
        raise ValueError("REQUEST_NOT_OBJECT")
    if req.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("BAD_PROTOCOL_VERSION")
    action = req.get("action")
    if action not in ACTIONS:
        raise ValueError("UNKNOWN_ACTION")
    _reject_unknown_fields(req, action)
    if not isinstance(req.get("request_id"), str) or not req["request_id"]:
        raise ValueError("BAD_REQUEST_ID")
    if action == "helper-version":
        return None, None
    if action == "rollback-files":
        if "dry_run" in req and not isinstance(req.get("dry_run"), bool):
            raise ValueError("BAD_DRY_RUN")
        rb.validate_backup_id(req.get("backup_id"))
        return None, None
    if req.get("app_version") != APP_VERSION:
        raise ValueError("BAD_APP_VERSION")
    if not isinstance(req.get("dry_run"), bool):
        raise ValueError("BAD_DRY_RUN")
    rollback = req.get("rollback")
    if not isinstance(rollback, dict) or rollback.get("mode") != "timeshift_or_file_backup":
        raise ValueError("BAD_ROLLBACK_MODE")
    swap_req = None
    if "swap_file_request" in req:
        swap_req = SwapFileRequest.from_dict(req.get("swap_file_request"))
    files = req.get("planned_files")
    if not isinstance(files, list) or any(not isinstance(f, str) for f in files):
        raise ValueError("BAD_PLANNED_FILES")
    if len(files) != len(set(files)):
        raise ValueError("DUPLICATE_PLANNED_FILES")
    allowed_files = set(MANAGED_FILES)
    required_files = set(MANAGED_FILES)
    if swap_req is not None:
        allowed_files.add(FSTAB_FILE)
        required_files.add(FSTAB_FILE)
    if set(files) - allowed_files:
        raise ValueError("UNSAFE_PLANNED_FILES")
    if not set(files).issuperset(required_files):
        raise ValueError("MISSING_MANAGED_FILES")
    steps = req.get("steps")
    if not isinstance(steps, list) or any(not isinstance(s, str) for s in steps):
        raise ValueError("BAD_STEPS")
    if len(steps) != len(set(steps)):
        raise ValueError("DUPLICATE_STEP_ID")
    if set(steps) - STEP_IDS:
        raise ValueError("UNKNOWN_STEP_ID")
    required_steps = {"validate_target", "create_rollback", "write_resume_config", "write_grub_config", "update_initramfs", "update_grub"}
    if swap_req is not None:
        required_steps.add("ensure_swap_file")
    if not set(steps).issuperset(required_steps):
        raise ValueError("MISSING_REQUIRED_STEPS")
    raw_target = req.get("selected_target")
    if not isinstance(raw_target, dict):
        raise ValueError("BAD_SELECTED_TARGET")
    target_fields = {f.name for f in SwapTarget.__dataclass_fields__.values()}
    unknown_target_fields = set(raw_target) - target_fields
    if unknown_target_fields:
        raise ValueError("UNKNOWN_TARGET_FIELDS:" + ",".join(sorted(unknown_target_fields)))
    target = SwapTarget.from_dict(raw_target)
    if target.kind not in {"partition", "file"}:
        raise ValueError("BAD_TARGET_KIND")
    if not isinstance(target.path, str) or not target.path.startswith("/"):
        raise ValueError("BAD_TARGET_PATH")
    if swap_req is None:
        if not target.uuid:
            raise ValueError("TARGET_UUID_REQUIRED")
        parsers.validate_uuid(str(target.uuid))
        if target.kind == "file" and (not isinstance(target.resume_offset, int) or target.resume_offset <= 0):
            raise ValueError("TARGET_OFFSET_REQUIRED")
        if not isinstance(target.active, bool) or not target.active:
            raise ValueError("TARGET_NOT_ACTIVE")
    else:
        if target.kind != "file" or target.path != swap_req.path:
            raise ValueError("SWAP_REQUEST_TARGET_MISMATCH")
    return target, swap_req

def _live_profile() -> object:
    return profile_from_probe_data(probe_current_system())


def _validate_target_live(target: SwapTarget) -> SwapTarget:
    """Re-probe and reclassify as root; never trust GUI-supplied status."""
    profile = _live_profile()
    matches = [c for c in profile.candidates if c.path == target.path and c.kind == target.kind]
    if not matches:
        raise ValueError("TARGET_NOT_ACTIVE")
    live = matches[0]
    if not live.selectable:
        reason = "; ".join(live.reasons or live.warnings or [live.status])
        raise ValueError("TARGET_NOT_SELECTABLE:" + reason)
    if live.uuid and target.uuid and live.uuid.lower() != target.uuid.lower():
        raise ValueError("TARGET_UUID_CHANGED")
    if live.kind == "file" and live.resume_offset != target.resume_offset:
        raise ValueError("TARGET_OFFSET_CHANGED")
    plan = build_modification_plan(profile, live)
    if not plan.can_apply:
        raise ValueError("PLAN_BLOCKED:" + "; ".join(plan.blocking_reasons))
    return live


def _rollback_files(req: dict) -> int:
    request_id = str(req.get("request_id", "unknown"))
    backup_id = rb.validate_backup_id(req.get("backup_id"))
    dry_run = bool(req.get("dry_run", False))
    try:
        _event(request_id, "hello", message="Ubuntu Hibernate Wizard helper ready", app_version=APP_VERSION, protocol_version=PROTOCOL_VERSION)
        _event(request_id, "step", step_id="create_rollback", status="running", progress=0.05, message=f"Loading rollback manifest {backup_id}")
        manifest = rb.validate_manifest_security(backup_id)
        actions = rb.RollbackPlanner().build_plan(manifest)
        if dry_run:
            for idx, action in enumerate(actions, start=1):
                _event(request_id, "rollback-preview", status=action.status, progress=min(0.95, idx / max(1, len(actions))), message=f"{action.type} {action.path or ''}: {action.reason or ''}", action=action.asdict())
            _event(request_id, "complete", status="success", progress=1.0, message="Rollback dry-run completed")
            return 0

        def emit(percent, line):
            _event(request_id, "rollback-progress", status="running", progress=float(percent) / 100.0, message=line)

        helper = Helper()
        result = helper.cmd_rollback({"backup_id": backup_id, "mode": "safe"}, emit)
        if result.get("success"):
            _event(request_id, "complete", status="success", progress=1.0, message=result.get("message", "Rollback completed"), data=result.get("data"))
            return 0
        _event(request_id, "error", status="error", progress=1.0, message=result.get("message") or result.get("error_code") or "Rollback failed")
        return 1
    except Exception as exc:  # noqa: BLE001
        _event(request_id, "error", status="error", progress=1.0, message=str(exc))
        return 1


def _atomic_write_v042(path: str, content: str, bm: rb.BackupManager) -> bool:
    if path not in MANAGED_FILES and path != FSTAB_FILE:
        raise rb.RollbackSecurityError("UNSAFE_MANAGED_FILE")
    bm.record_before_write(path, managed_by_wizard=True)
    old = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
    changed = old != content
    if changed:
        rb.atomic_write_bytes(path, content.encode("utf-8"), mode=0o644, uid=0, gid=0)
    bm.record_after_write(path)
    return changed


def _is_active_swap(path: str) -> bool:
    try:
        active = [d.name for d in parsers.parse_swapon_show_bytes(run(["swapon", "--show", "--bytes"]).stdout)]
    except Exception:  # noqa: BLE001
        return False
    return path in active


def _ensure_fstab_entry(path: str, bm: rb.BackupManager | None, *, dry_run: bool) -> bool:
    old = Path(FSTAB_FILE).read_text(encoding="utf-8") if Path(FSTAB_FILE).exists() else ""
    new, changed = system.ensure_swap_entry(old, path)
    if changed and not dry_run:
        assert bm is not None
        _atomic_write_v042(FSTAB_FILE, new, bm)
    return changed


def _run_checked(argv: list[str], *, timeout: int = 120) -> None:
    r = run(argv, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "command failed").strip())


def _format_gib(size_bytes: int) -> str:
    return f"{size_bytes / GIB:.1f} GiB"


def _preflight_swapfile_free_space(path: str, size_bytes: int, *, needs_new_file: bool) -> None:
    """Fail before swapoff/rename/boot writes if the requested swap file cannot fit."""
    if not needs_new_file:
        return
    parent = str(Path(path).parent)
    try:
        usage = shutil.disk_usage(parent)
    except OSError as exc:
        raise RuntimeError("CANNOT_VERIFY_FREE_SPACE") from exc
    required = int(size_bytes) + int(MIN_ROOT_FREE_AFTER_SWAPFILE_BYTES)
    if usage.free < required:
        raise RuntimeError(
            "INSUFFICIENT_FREE_SPACE_FOR_SWAPFILE:"
            f"available={_format_gib(usage.free)},"
            f"required={_format_gib(required)},"
            f"swap={_format_gib(size_bytes)},"
            f"reserve={_format_gib(MIN_ROOT_FREE_AFTER_SWAPFILE_BYTES)}"
        )


def _make_swap_file(path: str, size_bytes: int) -> None:
    # The helper is root-only here.  Refuse symlinks/non-regular files before writing.
    p = Path(path)
    if p.exists() and (p.is_symlink() or not p.is_file()):
        raise RuntimeError("UNSAFE_SWAPFILE_PATH")
    if not p.exists():
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    os.chmod(path, 0o600)
    r = run(["fallocate", "-l", str(size_bytes), path], timeout=600)
    if r.returncode != 0:
        # Fallback for filesystems where fallocate is unavailable but sparse
        # files are not acceptable: write zeroes through dd.
        mib = size_bytes // (1024 ** 2)
        r = run(["dd", "if=/dev/zero", f"of={path}", "bs=1M", f"count={mib}", "status=none"], timeout=1200)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "failed to allocate swap file").strip())
    os.chmod(path, 0o600)
    _run_checked(["mkswap", path], timeout=120)


def _ensure_managed_swap_file(request: SwapFileRequest, bm: rb.BackupManager | None, *, dry_run: bool, emit, request_id: str) -> None:
    path = request.path
    size = request.size_bytes
    rb.validate_swap_path(path)
    parent = str(Path(path).parent)
    findmnt = run(["findmnt", "-no", "SOURCE,FSTYPE,UUID", "-T", parent])
    if findmnt.returncode != 0:
        raise RuntimeError("CANNOT_DETECT_SWAPFILE_FILESYSTEM")
    _source, fstype, _uuid = parsers.parse_findmnt_target(findmnt.stdout)
    if fstype != "ext4":
        raise RuntimeError(f"UNSUPPORTED_SWAPFILE_FILESYSTEM:{fstype}")
    p = Path(path)
    if p.exists() and (p.is_symlink() or not p.is_file()):
        raise RuntimeError("UNSAFE_SWAPFILE_PATH")
    existing_size = p.stat().st_size if p.exists() else 0
    active_before = _is_active_swap(path)
    needs_new_file = (not p.exists()) or existing_size != size
    _preflight_swapfile_free_space(path, size, needs_new_file=needs_new_file)
    fstab_changed = _ensure_fstab_entry(path, bm, dry_run=dry_run)
    if dry_run:
        message = f"Dry-run: would {'create/resize' if needs_new_file else 'keep'} {path} at {size // (1024 ** 3)} GiB"
        if fstab_changed:
            message += " and ensure /etc/fstab entry"
        _event(request_id, "step", step_id="ensure_swap_file", status="skipped", progress=0.38, message=message)
        return
    assert bm is not None
    bm._manifest.swap = {
        "path": path,
        "mode": "restore-retained-old-file" if p.exists() and needs_new_file else "remove-wizard-created-swap" if not p.exists() else "none",
        "existed_before": p.exists(),
        "was_active_before": active_before,
        "old_swap_backup_name": None,
        "side_file_name": None,
        "rollback_current_name": None,
        "target_size_bytes": size,
    }
    bm.save()
    old_path = None
    if needs_new_file:
        if active_before:
            _run_checked(["swapoff", path], timeout=180)
        if p.exists():
            old_name = rb.expected_old_swap_backup_name(path, bm.backup_id)
            old_path = p.with_name(old_name)
            os.replace(path, old_path)
            os.chmod(old_path, 0o600)
            bm._manifest.swap["old_swap_backup_name"] = old_name
            bm.save()
        try:
            _make_swap_file(path, size)
        except Exception:
            # Best effort immediate restore if allocation failed before swapon.
            if old_path and old_path.exists() and not p.exists():
                os.replace(old_path, path)
                os.chmod(path, 0o600)
                if active_before:
                    run(["swapon", path], timeout=180)
            raise
    if not _is_active_swap(path):
        _run_checked(["swapon", path], timeout=180)
    _event(request_id, "step", step_id="ensure_swap_file", status="success", progress=0.38, message=f"Managed swap file ready: {path} ({size // (1024 ** 3)} GiB)")


def _select_live_swapfile_target(path: str) -> SwapTarget:
    profile = _live_profile()
    matches = [c for c in profile.candidates if c.path == path and c.kind == "file"]
    if not matches:
        raise ValueError("TARGET_NOT_ACTIVE")
    live = matches[0]
    if not live.selectable:
        reason = "; ".join(live.reasons or live.warnings or [live.status])
        raise ValueError("TARGET_NOT_SELECTABLE:" + reason)
    plan = build_modification_plan(profile, live)
    if not plan.can_apply:
        raise ValueError("PLAN_BLOCKED:" + "; ".join(plan.blocking_reasons))
    return live


def run_one_shot(req: dict) -> int:
    request_id = str(req.get("request_id", "unknown"))
    try:
        if req.get("action") == "helper-version":
            _validate_one_shot_request(req)
            _event(request_id, "hello", message="helper-version", app_version=APP_VERSION, protocol_version=PROTOCOL_VERSION)
            return 0
        if req.get("action") == "rollback-files":
            _validate_one_shot_request(req)
            return _rollback_files(req)
        target, swap_req = _validate_one_shot_request(req)
        assert target is not None
        dry_run = bool(req.get("dry_run", False))
        action = req.get("action")
        _event(request_id, "hello", message="Ubuntu Hibernate Wizard helper ready", app_version=APP_VERSION, protocol_version=PROTOCOL_VERSION)

        if action == "validate-plan":
            if swap_req is not None:
                p = Path(swap_req.path)
                existing_size = p.stat().st_size if p.exists() and p.is_file() else 0
                needs_new_file = (not p.exists()) or existing_size != swap_req.size_bytes
                _preflight_swapfile_free_space(swap_req.path, swap_req.size_bytes, needs_new_file=needs_new_file)
                _event(request_id, "plan-valid", step_id="validate_target", status="success", progress=0.5, message="Managed swap-file request is structurally valid and free-space preflight passed; live UUID/offset validation happens during real apply after creation")
            else:
                _event(request_id, "step", step_id="validate_target", status="running", progress=0.10, message="Re-probing and validating selected swap target")
                _validate_target_live(target)
                _event(request_id, "plan-valid", step_id="validate_target", status="success", progress=0.5, message="Plan validation succeeded")
            _event(request_id, "complete", status="success", progress=1.0, message="Plan is valid")
            return 0

        bm = None
        if swap_req is not None:
            if dry_run:
                _event(request_id, "rollback-ready", step_id="create_rollback", status="skipped", progress=0.20, message="Dry-run: rollback snapshot not created")
            else:
                _event(request_id, "step", step_id="create_rollback", status="running", progress=0.12, message="Creating rollback manifest")
                bm = rb.BackupManager.begin("apply", app_version=APP_VERSION)
                _event(request_id, "rollback-ready", step_id="create_rollback", status="success", progress=0.20, message="Rollback snapshot created", backup_id=bm.backup_id)
            _event(request_id, "step", step_id="ensure_swap_file", status="running", progress=0.26, message=f"Preparing managed swap file {swap_req.path}")
            _ensure_managed_swap_file(swap_req, bm, dry_run=dry_run, emit=None, request_id=request_id)
            if dry_run:
                _event(request_id, "step", step_id="validate_target", status="skipped", progress=0.45, message="Dry-run: target validation will happen after swap-file creation during real apply")
                for step, path_, prog in (("write_resume_config", RESUME_FILE, 0.58), ("write_grub_config", GRUB_FRAGMENT, 0.68)):
                    _event(request_id, "step", step_id=step, status="skipped", progress=prog, message=f"Dry-run: would write {path_} after live UUID/offset detection")
                for step, argv, prog in (("update_initramfs", ["update-initramfs", "-u"], 0.82), ("update_grub", ["update-grub"], 0.94)):
                    _event(request_id, "command", step_id=step, status="skipped", progress=prog, message="Dry-run: command not executed: " + " ".join(argv))
                _event(request_id, "complete", status="success", progress=1.0, message="Dry-run completed. Real apply would require authentication and a manual reboot afterward.")
                return 0
            target = _select_live_swapfile_target(swap_req.path)
            _event(request_id, "plan-valid", step_id="validate_target", status="success", progress=0.45, message="Managed swap file validated with live UUID and resume_offset")
        else:
            _event(request_id, "step", step_id="validate_target", status="running", progress=0.05, message="Re-probing and validating selected swap target")
            target = _validate_target_live(target)
            _event(request_id, "plan-valid", step_id="validate_target", status="success", progress=0.15, message="Plan validation succeeded")
            if dry_run:
                _event(request_id, "rollback-ready", step_id="create_rollback", status="skipped", progress=0.25, message="Dry-run: rollback snapshot not created")
            else:
                _event(request_id, "step", step_id="create_rollback", status="running", progress=0.20, message="Creating rollback manifest")
                bm = rb.BackupManager.begin("apply", app_version=APP_VERSION)
                _event(request_id, "rollback-ready", step_id="create_rollback", status="success", progress=0.30, message="Rollback snapshot created", backup_id=bm.backup_id)

        resume_content = generated_resume_config(target)
        grub_content = generated_grub_fragment(target)
        for step, path, content, prog in (
            ("write_resume_config", RESUME_FILE, resume_content, 0.58 if swap_req else 0.45),
            ("write_grub_config", GRUB_FRAGMENT, grub_content, 0.68 if swap_req else 0.60),
        ):
            _event(request_id, "step", step_id=step, status="running", progress=prog - 0.06, message=f"Writing {path}")
            if dry_run:
                _event(request_id, "step", step_id=step, status="skipped", progress=prog, message=f"Dry-run: would write {path}")
            else:
                changed = _atomic_write_v042(path, content, bm)
                _event(request_id, "step", step_id=step, status="success", progress=prog, message=("Changed " if changed else "Already current ") + path)

        for step, argv, prog in (
            ("update_initramfs", ["update-initramfs", "-u"], 0.82 if swap_req else 0.78),
            ("update_grub", ["update-grub"], 0.94 if swap_req else 0.92),
        ):
            _event(request_id, "command", step_id=step, status="running", progress=prog - 0.06, message="Running " + " ".join(argv))
            if dry_run:
                _event(request_id, "command", step_id=step, status="skipped", progress=prog, message="Dry-run: command not executed")
                continue
            r = run(argv, timeout=900 if step == "update_initramfs" else 180)
            if r.returncode != 0 and step == "update_grub" and shutil.which("grub-mkconfig"):
                r = run(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"], timeout=180)
            if r.returncode != 0:
                if bm:
                    bm.mark_status("failed", failed_step=step, error_code="COMMAND_FAILED", message=r.stderr.strip() or r.stdout.strip())
                _event(request_id, "error", step_id=step, status="error", progress=prog, message="Command failed", stdout_tail=r.stdout[-1000:], stderr_tail=r.stderr[-1000:])
                return 1
            _event(request_id, "command", step_id=step, status="success", progress=prog, message="Command completed", stdout_tail=r.stdout[-1000:], stderr_tail=r.stderr[-1000:])

        if bm:
            bm.mark_status("completed")
        _event(request_id, "complete", status="success", progress=1.0, message="Apply completed. Reboot manually to test hibernation.")
        return 0
    except Exception as exc:  # noqa: BLE001
        _event(request_id, "error", status="error", progress=1.0, message=str(exc))
        return 1



if __name__ == "__main__":
    if "--action" in sys.argv:
        try:
            action = sys.argv[sys.argv.index("--action") + 1]
        except (ValueError, IndexError):
            print("missing --action value", file=sys.stderr)
            sys.exit(2)
        if action != "helper-version" and os.geteuid() != 0:
            print("must run as root via pkexec", file=sys.stderr)
            sys.exit(1)
        if "--stdin-json" in sys.argv:
            payload = json.loads(sys.stdin.read() or "{}")
        else:
            payload = {"protocol_version": PROTOCOL_VERSION, "request_id": "helper-version", "action": action}
        payload.setdefault("action", action)
        sys.exit(run_one_shot(payload))
    if os.geteuid() != 0:
        print("must run as root via pkexec", file=sys.stderr)
        sys.exit(1)
    sys.exit(Helper().serve())
