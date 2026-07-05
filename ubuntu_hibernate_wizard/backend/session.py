"""GUI-side client for the persistent privileged helper (SS26.1).
Launches pkexec ONCE, speaks JSON Lines, relays progress callbacks."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

HELPER = "/usr/libexec/ubuntu-hibernate-wizard/privileged-helper"
BACKUP_DIR_BASE = "/var/backups/ubuntu-hibernate-wizard"


@dataclass
class DetectInfo:
    rows: list = field(default_factory=list)
    secure_boot: bool = False
    ram_bytes: int = 16 * 1024**3
    swap_file: str = "/swap.img"
    hard_stop: bool = False


class HelperSession:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._rid = 0
        self._last_verify: dict | None = None

    # ------------------------------------------------ transport
    def _ensure(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        self._proc = subprocess.Popen(          # single elevation (SS26.1)
            ["pkexec", HELPER], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, text=True, bufsize=1)

    def request(self, cmd: str, args: dict | None = None,
                on_progress=None) -> dict:
        self._ensure()
        self._rid += 1
        self._proc.stdin.write(json.dumps(
            {"request_id": self._rid, "cmd": cmd, "args": args or {}}) + "\n")
        self._proc.stdin.flush()
        while True:
            line = self._proc.stdout.readline()
            if not line:
                return {"success": False, "error_code": "HELPER_DIED",
                        "message": "helper exited (authentication cancelled?)"}
            msg = json.loads(line)
            if msg.get("event") == "progress":
                if on_progress:
                    on_progress(msg.get("percent"), msg.get("line", ""))
                continue
            return msg

    # ------------------------------------------------ detection
    def detect(self) -> DetectInfo:
        r = self.request("detect")
        if not r.get("success"):
            raise RuntimeError(r.get("message") or r.get("error_code")
                               or "detection failed")
        d = r.get("data", {})
        sb = "enabled" in d.get("sb", "").lower()
        kernel_ok = "disk" in d.get("power_state", "")
        info = DetectInfo(secure_boot=sb, ram_bytes=d.get("ram_bytes",
                                                          16 * 1024**3))
        rows = [
            ("Kernel hibernate support", "'disk' in /sys/power/state",
             "success" if kernel_ok else "error",
             "OK" if kernel_ok else "Unsupported"),
            ("Root filesystem", d.get("root", "").strip() or "unknown",
             "success" if "ext4" in d.get("root", "") else "error",
             "ext4" if "ext4" in d.get("root", "") else "Unsupported"),
            ("GRUB", "/etc/default/grub",
             "success" if d.get("grub_exists") else "error",
             "Detected" if d.get("grub_exists") else "Missing"),
            ("initramfs-tools", "/etc/initramfs-tools",
             "success" if d.get("initramfs_tools") else "error",
             "Detected" if d.get("initramfs_tools") else "Missing"),
            ("Secure Boot", d.get("sb", "unknown") or "unknown",
             "warning" if sb else "success",
             "Enabled" if sb else "Disabled"),
        ]
        virt = d.get("virt", "none")
        if virt not in ("none", ""):
            rows.append(("Virtualization", f"detected: {virt}",
                         "warning", "VM"))
        info.rows = rows
        info.hard_stop = any(c == "error" for _, _, c, _ in rows)
        return info

    # ------------------------------------------------ plan / apply
    def build_plan(self, size_mb: int) -> list[str]:
        gb = size_mb / 1024
        return [
            f"Create /swap.img ({gb:.0f} GB) crash-safely and activate it",
            "Add swap entry to /etc/fstab",
            "Calculate resume UUID and swap-file offset",
            "Set resume parameters in GRUB and run update-grub",
            "Write initramfs resume config and run update-initramfs",
            "Allow hibernation in systemd sleep and polkit",
            f"Back up all modified files to {BACKUP_DIR_BASE}/<timestamp>/",
        ]

    def apply(self, size_mb: int, on_progress) -> tuple[bool, str]:
        import datetime
        backup = f"{BACKUP_DIR_BASE}/{datetime.datetime.now():%Y%m%d-%H%M%S}"
        plan = {"resize-swap": True, "update-fstab": True,
                "update-grub-resume": True, "update-initramfs-resume": True,
                "update-sleep-conf": True, "update-polkit-rule": True}
        r = self.request("submit-plan", {"plan": plan})
        if not r.get("success"):
            return False, r.get("message", "could not register plan")

        on_progress(2, "Creating swap file (old swap stays active)...")
        r = self.request("resize-swap",
                         {"swap_file": "/swap.img", "size_mb": size_mb},
                         on_progress)
        if not r.get("success"):
            return False, f"Swap creation failed: {r.get('error_code')}"
        offset = r["data"]["new_offset"]

        on_progress(60, "Verifying filesystem UUID...")
        v = self.request("verify", {"swap_file": "/swap.img"})
        if not v.get("success"):
            return False, "could not read filesystem UUID"
        uuid = v["data"]["fs_uuid"]

        on_progress(65, "Updating GRUB (resume=UUID, resume_offset)...")
        r = self.request("update-grub-resume",
                         {"uuid": uuid, "offset": offset,
                          "backup_dir": backup}, on_progress)
        if not r.get("success"):
            return False, f"GRUB update failed: {r.get('message','')}"

        on_progress(75, "Updating initramfs (takes a few minutes)...")
        r = self.request("update-initramfs-resume",
                         {"uuid": uuid, "offset": offset,
                          "backup_dir": backup}, on_progress)
        if not r.get("success"):
            return False, f"initramfs update failed: {r.get('message','')}"

        on_progress(100, "All changes applied - reboot required")
        return True, "ok"

    # ------------------------------------------------ verify / repair
    def verify(self) -> dict:
        r = self.request("verify", {"swap_file": "/swap.img"})
        if not r.get("success"):
            raise RuntimeError(r.get("message") or r.get("error_code")
                               or "verify failed")
        self._last_verify = r["data"]
        return r["data"]

    def repair(self) -> tuple[bool, str]:
        if not self._last_verify:
            return False, "run verification first"
        d = self._last_verify
        self.request("submit-plan", {"plan": {
            "update-grub-resume": True, "update-initramfs-resume": True}})
        import datetime
        backup = f"{BACKUP_DIR_BASE}/{datetime.datetime.now():%Y%m%d-%H%M%S}"
        for cmd in ("update-grub-resume", "update-initramfs-resume"):
            r = self.request(cmd, {"uuid": d["fs_uuid"],
                                   "offset": d["real_offset"],
                                   "backup_dir": backup})
            if not r.get("success"):
                return False, f"{cmd} failed"
        return True, "repaired - reboot required"

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.stdin.close()            # helper exits on EOF
