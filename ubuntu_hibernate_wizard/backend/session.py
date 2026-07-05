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
        size_gib = size_mb / 1024
        swap_file = "/swap.img"
        plan = {"resize-swap": True, "update-fstab": True,
                "update-grub-resume": True, "update-initramfs-resume": True,
                "update-sleep-conf": True, "update-polkit-rule": True,
                "reboot-system": True}

        on_progress(1, "Approved operation set: resize-swap, update-fstab, "
                       "update-grub-resume, update-initramfs-resume, "
                       "update-sleep-conf, update-polkit-rule, reboot-system")
        on_progress(1, f"Selected swap target: {swap_file}; requested size: "
                       f"{size_mb} MiB ({size_gib:.1f} GiB)")
        on_progress(1, f"Backups for changed system files will be written to: {backup}")
        r = self.request("submit-plan", {"plan": plan})
        if not r.get("success"):
            return False, r.get("message", "could not register plan")
        on_progress(2, "Plan registered with privileged helper; helper will reject "
                       "any operation outside this approved set")

        on_progress(3, "Step 1/6: building replacement swap file using safe "
                       "build-aside method; old swap stays active until validation")
        r = self.request("resize-swap",
                         {"swap_file": swap_file, "size_mb": size_mb},
                         on_progress)
        if not r.get("success"):
            return False, f"Swap creation failed: {r.get('error_code')}"
        offset = r["data"]["new_offset"]
        on_progress(58, f"Swap file active: {swap_file}; measured resume_offset={offset}")

        on_progress(60, f"Step 2/6: ensuring /etc/fstab has one active entry: "
                        f"{swap_file} none swap sw 0 0")
        r = self.request("update-fstab", {"swap_file": swap_file,
                                           "backup_dir": backup}, on_progress)
        if not r.get("success"):
            return False, f"fstab update failed: {r.get('message') or r.get('error_code')}"
        on_progress(62, "fstab result: " + ("changed" if r.get("changed") else "already correct"))

        on_progress(64, "Step 3/6: reading filesystem UUID and confirming ext4 "
                        "filesystem for the swap file")
        v = self.request("verify", {"swap_file": swap_file})
        if not v.get("success"):
            return False, "could not read filesystem UUID"
        uuid = v["data"]["fs_uuid"]
        on_progress(65, f"Resume identity calculated: resume=UUID={uuid}; "
                        f"resume_offset={offset}")

        on_progress(68, "Step 4/6: editing /etc/default/grub: remove stale "
                        "resume/resume_offset values, preserve unrelated kernel "
                        "parameters, add the new resume values, then run update-grub")
        r = self.request("update-grub-resume",
                         {"uuid": uuid, "offset": offset,
                          "backup_dir": backup}, on_progress)
        if not r.get("success"):
            return False, f"GRUB update failed: {r.get('message','')}"
        on_progress(74, "GRUB result: " + ("changed and regenerated" if r.get("changed") else "already contained current resume values"))

        on_progress(76, "Step 5/6: writing /etc/initramfs-tools/conf.d/resume "
                        "with exact RESUME UUID and offset, then running "
                        "update-initramfs -u -k all")
        r = self.request("update-initramfs-resume",
                         {"uuid": uuid, "offset": offset,
                          "backup_dir": backup}, on_progress)
        if not r.get("success"):
            return False, f"initramfs update failed: {r.get('message','')}"
        on_progress(88, "initramfs result: resume config written and initramfs images regenerated")

        on_progress(90, "Step 6/6: enabling hibernation policy: write systemd sleep override and polkit logind hibernate rule")
        r = self.request("update-sleep-conf", {"backup_dir": backup}, on_progress)
        if not r.get("success"):
            return False, f"systemd sleep config failed: {r.get('message') or r.get('error_code')}"
        on_progress(94, "systemd sleep config result: " + ("changed" if r.get("changed") else "already correct"))
        r = self.request("update-polkit-rule", {"backup_dir": backup}, on_progress)
        if not r.get("success"):
            return False, f"polkit rule update failed: {r.get('message') or r.get('error_code')}"
        on_progress(98, "polkit result: " + ("changed" if r.get("changed") else "already correct"))

        on_progress(100, "All changes applied - reboot required before testing resume")
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

    def reboot_now(self) -> tuple[bool, str]:
        r = self.request("reboot-system")
        if r.get("success"):
            return True, r.get("message", "reboot requested")
        return False, r.get("message") or r.get("error_code") or "reboot failed"

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.stdin.close()            # helper exits on EOF
