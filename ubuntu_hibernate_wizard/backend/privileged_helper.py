#!/usr/bin/env python3
"""Privileged helper (§20.1, §26.1). Launched ONCE per app run via pkexec.

Protocol: newline-delimited JSON on stdin/stdout.
  request : {"request_id": N, "cmd": "...", "args": {...}}
  progress: {"request_id": N, "event": "progress", "percent": P, "line": "..."}
  response: {"request_id": N, "success": bool, "changed": bool,
             "error_code": str|null, "message": str, "stdout": str,
             "stderr": str, "reboot_required": bool, "data": {...}}

Safety: exits when stdin closes; 15-min idle timeout; exclusive lock;
mutations only after submit-plan registered the approved plan (NOT_IN_PLAN).
No generic command execution is exposed.
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from ubuntu_hibernate_wizard.core import grub as grub_mod           # noqa: E402
from ubuntu_hibernate_wizard.core import parsers, system            # noqa: E402

LOCK_PATH = "/run/ubuntu-hibernate-wizard.lock"
IDLE_TIMEOUT = 15 * 60
ENV = {"LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}       # §20.8

MUTATING = {"create-swap", "resize-swap", "update-fstab", "update-grub-resume",
            "update-initramfs-resume", "update-sleep-conf",
            "update-polkit-rule", "rollback"}


def run(argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """§20.2: argument lists, timeouts, LC_ALL=C, full capture."""
    return subprocess.run(argv, check=False, capture_output=True,
                          text=True, timeout=timeout, env=ENV)


class Helper:
    def __init__(self) -> None:
        self.plan: dict | None = None

    # ------------- read-only subcommands
    def cmd_detect(self, args: dict) -> dict:
        data: dict = {}
        data["swapon"] = run(["swapon", "--show", "--bytes"]).stdout
        data["cmdline"] = open("/proc/cmdline").read().strip()
        data["power_state"] = self._read("/sys/power/state")
        data["virt"] = run(["systemd-detect-virt"]).stdout.strip()
        data["sb"] = run(["mokutil", "--sb-state"]).stdout.strip() \
            if shutil.which("mokutil") else "unknown"
        data["root"] = run(["findmnt", "-no", "SOURCE,FSTYPE,UUID", "/"]).stdout
        try:
            with open("/proc/meminfo") as f:
                for ln in f:
                    if ln.startswith("MemTotal:"):
                        data["ram_bytes"] = int(ln.split()[1]) * 1024
                        break
        except OSError:
            data["ram_bytes"] = 16 * 1024**3
        data["grub_exists"] = os.path.exists("/etc/default/grub")
        data["initramfs_tools"] = os.path.isdir("/etc/initramfs-tools")
        return {"success": True, "data": data}

    def cmd_verify(self, args: dict) -> dict:
        swap = self._valid_swap_path(args["swap_file"])
        out = run(["findmnt", "-no", "SOURCE,FSTYPE,UUID", "-T", swap])
        _, fstype, uuid = parsers.parse_findmnt_target(out.stdout)
        if fstype != "ext4":
            return {"success": False, "error_code": "UNSUPPORTED_FS",
                    "message": f"swap file is on {fstype}, ext4 required"}
        offset = parsers.parse_filefrag_offset(run(["filefrag", "-v", swap]).stdout)
        active = [d.name for d in parsers.parse_swapon_show_bytes(
            run(["swapon", "--show", "--bytes"]).stdout)]
        initrd = self._read("/etc/initramfs-tools/conf.d/resume")
        result = system.verify(swap, active, uuid,
                               offset, open("/proc/cmdline").read(), initrd)
        return {"success": True, "data": {
            "all_ok": result.all_ok, "errors": result.errors,
            "real_offset": offset, "fs_uuid": uuid,
            "checks": {"swap": result.active_swap_ok,
                       "uuid": result.resume_uuid_ok,
                       "offset": result.resume_offset_ok,
                       "initramfs": result.initramfs_resume_ok}}}

    # ------------- plan gating (§26.1.5)
    def cmd_submit_plan(self, args: dict) -> dict:
        self.plan = args["plan"]  # dict of approved step names -> params
        return {"success": True, "message": "plan registered"}

    def _require_plan(self, cmd: str, args: dict) -> None:
        if not self.plan or cmd not in self.plan:
            raise PermissionError("NOT_IN_PLAN")
        # helper-side revalidation (§20.1)
        if "swap_file" in args:
            self._valid_swap_path(args["swap_file"])
        if "uuid" in args:
            parsers.validate_uuid(args["uuid"])
        if "offset" in args and (not isinstance(args["offset"], int)
                                 or args["offset"] <= 0):
            raise ValueError("invalid offset")

    # ------------- mutating subcommands (abbreviated set)
    def cmd_update_grub_resume(self, args: dict, emit) -> dict:
        path = "/etc/default/grub"
        original = self._read(path)
        new = grub_mod.set_resume_params(
            original, args["uuid"], args["offset"],
            remove_noresume=args.get("remove_noresume", False))
        if new == original:
            return {"success": True, "changed": False}
        self._atomic_write(path, new, backup=args["backup_dir"])
        emit(50, "wrote /etc/default/grub, running update-grub")
        r = run(["update-grub"], timeout=180)
        if r.returncode != 0:
            return {"success": False, "error_code": "UPDATE_GRUB_FAILED",
                    "message": "update-grub returned non-zero exit status",
                    "stdout": r.stdout, "stderr": r.stderr}
        return {"success": True, "changed": True, "reboot_required": True,
                "stdout": r.stdout}

    def cmd_update_initramfs_resume(self, args: dict, emit) -> dict:
        path = "/etc/initramfs-tools/conf.d/resume"
        content = f"RESUME=UUID={args['uuid']} resume_offset={args['offset']}\n"
        self._atomic_write(path, content, backup=args["backup_dir"])
        emit(30, "running update-initramfs -u -k all (this takes a while)")
        r = run(["update-initramfs", "-u", "-k", "all"], timeout=900)
        if r.returncode != 0:
            return {"success": False, "error_code": "UPDATE_INITRAMFS_FAILED",
                    "message": "update-initramfs failed",
                    "stdout": r.stdout, "stderr": r.stderr}
        return {"success": True, "changed": True, "reboot_required": True}

    def cmd_resize_swap(self, args: dict, emit) -> dict:
        """Crash-safe build-aside resize (§26.2). Journaled at each phase."""
        target = self._valid_swap_path(args["swap_file"])
        side = target + ".new"
        size_mb = int(args["size_mb"])
        j = system.ResizeJournal(target, side, size_mb * 1024 * 1024, "building")
        j.save()
        emit(1, f"building {side} ({size_mb} MB) — existing swap stays active")
        r = run(["dd", "if=/dev/zero", f"of={side}", "bs=1M",
                 f"count={size_mb}", "conv=fsync"], timeout=7200)
        if r.returncode != 0:
            os.unlink(side); system.ResizeJournal.clear()
            return {"success": False, "error_code": "DD_FAILED",
                    "stderr": r.stderr}
        os.chmod(side, 0o600)
        run(["mkswap", side])
        # validate before touching old swap
        if run(["swapon", side]).returncode != 0:
            os.unlink(side); system.ResizeJournal.clear()
            return {"success": False, "error_code": "NEW_SWAP_INVALID"}
        run(["swapoff", side])
        j.phase = "switching"; j.save()
        emit(90, "switching over")
        run(["swapoff", target])                     # ok if absent
        os.replace(side, target)                     # atomic, extents preserved
        if run(["swapon", target]).returncode != 0:
            return {"success": False, "error_code": "SWAPON_FAILED"}
        j.phase = "activated"; j.save()
        offset = parsers.parse_filefrag_offset(
            run(["filefrag", "-v", target]).stdout)  # final path (§20.9.3)
        system.ResizeJournal.clear()
        emit(100, "swap replaced")
        return {"success": True, "changed": True,
                "data": {"new_offset": offset}}

    # ------------- utilities
    @staticmethod
    def _valid_swap_path(p: str) -> str:
        if p not in ("/swap.img", "/swapfile"):     # §10, advanced mode TODO
            raise ValueError("swap path not allowed")
        return p

    @staticmethod
    def _read(path: str) -> str:
        try:
            return open(path).read()
        except FileNotFoundError:
            return ""

    @staticmethod
    def _atomic_write(path: str, content: str, backup: str) -> None:
        """§20.6 atomic edit with backup."""
        os.makedirs(backup, exist_ok=True)
        if os.path.exists(path):
            shutil.copy2(path, os.path.join(backup, os.path.basename(path)))
        tmp = path + ".uhw-tmp"
        with open(tmp, "w") as f:
            f.write(content); f.flush(); os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)

    # ------------- session loop
    def serve(self) -> int:
        lock = open(LOCK_PATH, "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)     # §20.10
        except BlockingIOError:
            print(json.dumps({"request_id": 0, "success": False,
                              "error_code": "LOCKED"}), flush=True)
            return 1
        last = time.time()
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 30)
            if not r:
                if time.time() - last > IDLE_TIMEOUT:
                    return 0                                     # idle exit
                continue
            line = sys.stdin.readline()
            if not line:
                return 0                                         # GUI gone
            last = time.time()
            try:
                req = json.loads(line)
                rid, cmd = req["request_id"], req["cmd"]
                args = req.get("args", {})
                emit = lambda p, msg, _rid=rid: print(json.dumps(
                    {"request_id": _rid, "event": "progress",
                     "percent": p, "line": msg}), flush=True)
                if cmd in MUTATING:
                    self._require_plan(cmd, args)
                fn = getattr(self, "cmd_" + cmd.replace("-", "_"), None)
                if fn is None:
                    resp = {"success": False, "error_code": "UNKNOWN_CMD"}
                else:
                    resp = fn(args, emit) if cmd in MUTATING else fn(args)
            except PermissionError:
                resp = {"success": False, "error_code": "NOT_IN_PLAN",
                        "message": "operation not in the approved plan"}
            except Exception as e:                               # noqa: BLE001
                resp = {"success": False, "error_code": "INTERNAL",
                        "message": str(e)}
            resp.setdefault("changed", False)
            resp.setdefault("reboot_required", False)
            resp["request_id"] = rid
            print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("must run as root via pkexec", file=sys.stderr)
        sys.exit(1)
    sys.exit(Helper().serve())
