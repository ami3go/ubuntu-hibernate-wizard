"""Fixture and real-system conversion for hibernation system profiles.

The GUI must not request polkit authentication during normal System Check.  This
module therefore contains an unprivileged probe used by the GUI, fake-system
fixture loading, and conversion of raw helper/probe dictionaries into pure
SystemProfile objects.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ubuntu_hibernate_wizard.constants import RESUME_FILE
from ubuntu_hibernate_wizard.core import parsers
from ubuntu_hibernate_wizard.core.parsers import parse_swapon_show_bytes
from .encryption_detector import classify_encryption_for_swap
from .swap_detector import classify_swap_targets
from .swap_target_model import SystemProfile

ENV = {"LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}


def _run(argv: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a fixed argv list for read-only probing."""
    return subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout, env=ENV)


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return ""




def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def _fixture_read(root: Path, relative: str) -> str:
    path = root / relative
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _ram_from_meminfo(text: str) -> int:
    for ln in (text or "").splitlines():
        if ln.startswith("MemTotal:"):
            try:
                return int(ln.split()[1]) * 1024
            except (IndexError, ValueError):
                break
    return 16 * 1024**3


def load_fake_system(path: str | Path) -> SystemProfile:
    """Load either legacy JSON fixture or Rev-B fake-system directory."""
    p = Path(path)
    if p.is_dir():
        return profile_from_probe_data(load_fake_system_data(p))
    raw = json.loads(p.read_text(encoding="utf-8"))
    return SystemProfile.from_dict(raw) if "candidates" in raw else profile_from_probe_data(raw)


def load_fake_system_data(root: str | Path) -> dict[str, Any]:
    """Load a structured fake-system fixture directory into probe_data."""
    root = Path(root)
    metadata: dict[str, Any] = {}
    meta_path = root / "fixture.json"
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    meminfo = _fixture_read(root, "files/proc-meminfo.txt")
    data: dict[str, Any] = {
        "fixture_name": root.name,
        "swapon": _fixture_read(root, "commands/swapon-show.txt") or _fixture_read(root, "files/proc-swaps.txt"),
        "proc_swaps": _fixture_read(root, "files/proc-swaps.txt"),
        "cmdline": _fixture_read(root, "files/proc-cmdline.txt"),
        "power_state": _fixture_read(root, "files/sys-power-state.txt") or "freeze mem disk",
        "sys_power_resume": _fixture_read(root, "files/sys-power-resume.txt"),
        "lockdown": metadata.get("lockdown", "unknown"),
        "sb": metadata.get("secure_boot", "unknown"),
        "root": _fixture_read(root, "commands/findmnt-root.txt"),
        "kernel": metadata.get("kernel", "fixture-kernel"),
        "timeshift_available": bool(metadata.get("timeshift_available", False)),
        "initramfs_resume": _fixture_read(root, "files/etc-initramfs-resume.txt"),
        "fstab": _fixture_read(root, "files/etc-fstab.txt"),
        "crypttab": _fixture_read(root, "files/etc-crypttab.txt"),
        "grub_default": _fixture_read(root, "files/etc-default-grub.txt"),
        "os_release": _fixture_read(root, "files/etc-os-release.txt"),
        "lsblk_json": _fixture_read(root, "commands/lsblk.json"),
        "findmnt_json": _fixture_read(root, "commands/findmnt.json"),
        "findmnt_root": _fixture_read(root, "commands/findmnt-root.txt"),
        "dmsetup_info": _fixture_read(root, "commands/dmsetup-info.txt"),
        "filefrag": _fixture_read(root, "commands/filefrag.txt"),
        "ram_bytes": int(metadata.get("ram_bytes") or _ram_from_meminfo(meminfo)),
        "bootloader": metadata.get("bootloader", "grub"),
        "initramfs": metadata.get("initramfs", "initramfs-tools"),
        "distro": metadata.get("distro", "ubuntu"),
        "distro_version": metadata.get("distro_version", "Ubuntu fixture"),
        "grub_exists": metadata.get("grub_exists", True),
        "update_grub_exists": metadata.get("update_grub_exists", True),
        "initramfs_tools": metadata.get("initramfs_tools", True),
        "update_initramfs_exists": metadata.get("update_initramfs_exists", True),
        "read_only_config": bool(metadata.get("read_only_config", False)),
    }
    details_path = root / "commands/swap-details.json"
    if details_path.exists():
        data["swap_details"] = json.loads(details_path.read_text(encoding="utf-8"))
    data["swap_details"] = probe_swap_details_from_data(data)
    return data


def probe_current_system() -> dict:
    """Collect read-only system facts without pkexec.

    Missing permissions are represented as missing fields/probe errors; the
    planner then blocks uncertain targets instead of asking for root during the
    System Check page.  The privileged helper repeats the probe and validation
    before real apply.
    """
    data: dict = {}
    data["swapon"] = _run(["swapon", "--show", "--bytes"]).stdout
    data["proc_swaps"] = _read("/proc/swaps")
    data["cmdline"] = _read("/proc/cmdline").strip()
    data["power_state"] = _read("/sys/power/state")
    data["sys_power_resume"] = _read("/sys/power/resume")
    data["lockdown"] = _read("/sys/kernel/security/lockdown").strip() or "unknown"
    data["virt"] = _run(["systemd-detect-virt"]).stdout.strip() if shutil.which("systemd-detect-virt") else "unknown"
    data["sb"] = _run(["mokutil", "--sb-state"]).stdout.strip() if shutil.which("mokutil") else "unknown"
    data["root"] = _run(["findmnt", "-no", "SOURCE,FSTYPE,UUID", "/"]).stdout if shutil.which("findmnt") else ""
    data["findmnt_root"] = data["root"]
    data["kernel"] = _run(["uname", "-r"]).stdout.strip()
    data["timeshift_available"] = bool(shutil.which("timeshift"))
    data["initramfs_resume"] = _read(RESUME_FILE)
    data["fstab"] = _read("/etc/fstab")
    data["crypttab"] = _read("/etc/crypttab")
    data["grub_default"] = _read("/etc/default/grub")
    os_release = _read("/etc/os-release")
    data["os_release"] = os_release
    for line in os_release.splitlines():
        if line.startswith("PRETTY_NAME="):
            data["distro_version"] = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("ID="):
            data["distro"] = line.split("=", 1)[1].strip().strip('"')
    try:
        for ln in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if ln.startswith("MemTotal:"):
                data["ram_bytes"] = int(ln.split()[1]) * 1024
                break
    except (OSError, ValueError):
        data["ram_bytes"] = 16 * 1024**3

    data["grub_exists"] = os.path.exists("/etc/default/grub") or os.path.isdir("/etc/default/grub.d")
    data["update_grub_exists"] = bool(shutil.which("update-grub"))
    data["grub_mkconfig_exists"] = bool(shutil.which("grub-mkconfig"))
    data["bootloader"] = "grub" if data["grub_exists"] and data["update_grub_exists"] else "unknown"
    data["initramfs_tools"] = os.path.isdir("/etc/initramfs-tools") and bool(shutil.which("update-initramfs"))
    data["update_initramfs_exists"] = bool(shutil.which("update-initramfs"))
    data["initramfs"] = "initramfs-tools" if data["initramfs_tools"] else "unknown"
    if shutil.which("lsblk"):
        data["lsblk_json"] = _run(["lsblk", "--json", "-o", "NAME,KNAME,TYPE,FSTYPE,UUID,PARTUUID,MOUNTPOINTS,SIZE,PKNAME"]).stdout
    if shutil.which("dmsetup"):
        data["dmsetup_info"] = _run(["dmsetup", "info", "--columns", "--noheadings", "-o", "name,uuid,blkdevname"], timeout=20).stdout
    else:
        data["dmsetup_info"] = ""
    data["swap_details"] = probe_swap_details_from_data(data)
    return data


def _root_source(data: dict) -> str | None:
    root = data.get("findmnt_root") or data.get("root") or ""
    parts = str(root).split()
    return parts[0] if parts else None


def probe_swap_details_from_data(data: dict) -> dict[str, dict]:
    """Return per-swap facts keyed by path from real or fake probe data."""
    swapon_text = data.get("swapon", "")
    details: dict[str, dict] = {}
    try:
        devices = parsers.parse_swapon_show_bytes(swapon_text)
    except Exception:
        return details
    root_source = _root_source(data)
    supplied = dict(data.get("swap_details") or {})
    for dev in devices:
        item: dict = dict(supplied.get(dev.name, {}))
        item.setdefault("active", True)
        if dev.is_zram:
            item.update({"classification": "zram"})
            details[dev.name] = item
            continue
        if dev.type == "file":
            _populate_swapfile_details(dev.name, item, data)
        elif dev.type == "partition":
            _populate_partition_details(dev.name, item, data)
        prior_warnings = list(item.get("warnings") or [])
        prior_blockers = list(item.get("blockers") or [])
        enc = classify_encryption_for_swap(
            dev.name,
            crypttab_text=data.get("crypttab", ""),
            lsblk_json_text=data.get("lsblk_json", ""),
            dmsetup_info=data.get("dmsetup_info", ""),
            uuid=item.get("uuid"),
            partuuid=item.get("partuuid"),
            backing_device=item.get("backing_device") or item.get("source"),
            root_source=root_source,
        )
        item.update(enc)
        item["warnings"] = _dedupe(prior_warnings + list(enc.get("warnings") or []))
        item["blockers"] = _dedupe(prior_blockers + list(enc.get("blockers") or []))
        details[dev.name] = item
    return details


def probe_swap_details(swapon_text: str) -> dict[str, dict]:
    """Backward-compatible wrapper used by older tests and helper code."""
    return probe_swap_details_from_data({"swapon": swapon_text, "crypttab": "", "lsblk_json": "", "dmsetup_info": ""})



_RESUME_TOKEN_RE = re.compile(r"(?:^|\s)(?:resume|RESUME)=([^\s]+)")
_RESUME_OFFSET_RE = re.compile(r"(?:^|\s)resume_offset=(\d+)(?:\s|$)")


def _resume_uuid_from_value(value: str | None) -> str | None:
    if not value:
        return None
    if value.upper().startswith("UUID="):
        return value.split("=", 1)[1].lower()
    return None


def _resume_config_tokens(text: str) -> tuple[str | None, int | None]:
    """Return (resume UUID, resume_offset) from cmdline or initramfs text.

    Handles both kernel-style ``resume=UUID=...`` and initramfs-tools
    ``RESUME=UUID=...`` spellings.  Invalid offsets are ignored so the caller
    can keep the target blocked instead of accepting an unsafe value.
    """
    resume_match = _RESUME_TOKEN_RE.search(text or "")
    offset_match = _RESUME_OFFSET_RE.search(text or "")
    uuid = _resume_uuid_from_value(resume_match.group(1) if resume_match else None)
    offset = None
    if offset_match:
        try:
            value = int(offset_match.group(1))
            if value > 0:
                offset = value
        except ValueError:
            offset = None
    return uuid, offset


def _fstab_has_active_swapfile_entry(path: str, fstab_text: str) -> bool:
    for line in (fstab_text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) >= 3 and fields[0] == path and fields[2] == "swap":
            return True
    return False


def _offset_probe_was_permission_denied(item: dict) -> bool:
    return "permission denied" in str(item.get("offset_error", "")).lower()


def _apply_existing_resume_offset_fallback(path: str, item: dict, data: dict) -> None:
    """Use the already-booted resume_offset when unprivileged filefrag is blocked.

    On real Ubuntu systems, `/swap.img` is often mode 0600.  A normal GTK System
    Check can therefore fail `filefrag -v /swap.img` with PermissionError even
    when the system already has a working resume_offset in /proc/cmdline and
    initramfs-tools config.  This fallback only accepts that existing value when
    all of these are true:
      * filefrag failed specifically with a permission error, or a fake fixture
        is modelling that condition;
      * the active swap file is present in /etc/fstab;
      * cmdline and initramfs resume UUIDs, when present, match the backing FS;
      * cmdline and initramfs offsets, when both present, agree.

    The privileged helper still re-probes before real apply, so this is a GUI
    classification fallback rather than a blind write permission bypass.
    """
    if isinstance(item.get("resume_offset"), int) and item["resume_offset"] > 0:
        return
    if not _offset_probe_was_permission_denied(item):
        return
    if not _fstab_has_active_swapfile_entry(path, data.get("fstab", "")):
        return
    uuid = str(item.get("uuid") or "").lower()
    if not uuid:
        return

    cmd_uuid, cmd_offset = _resume_config_tokens(data.get("cmdline", ""))
    init_uuid, init_offset = _resume_config_tokens(data.get("initramfs_resume", ""))
    uuids = [u for u in (cmd_uuid, init_uuid) if u]
    if not uuids or any(u.lower() != uuid for u in uuids):
        return
    offsets = [o for o in (cmd_offset, init_offset) if isinstance(o, int) and o > 0]
    if not offsets or len(set(offsets)) != 1:
        return

    item["resume_offset"] = offsets[0]
    warnings = list(item.get("warnings") or [])
    warning = (
        "Using existing kernel/initramfs resume_offset because unprivileged "
        "filefrag cannot read the active swap file; the privileged helper will "
        "revalidate before real apply"
    )
    if warning not in warnings:
        warnings.append(warning)
    item["warnings"] = warnings
    item["offset_source"] = "existing_resume_config_after_filefrag_permission_denied"


def _populate_swapfile_details(path: str, item: dict, data: dict) -> None:
    if "filesystem" not in item and shutil.which("findmnt") and not data.get("fixture_name"):
        fm = _run(["findmnt", "-no", "SOURCE,FSTYPE,UUID", "-T", path])
        if fm.returncode == 0:
            try:
                src, fs, uuid = parsers.parse_findmnt_target(fm.stdout)
                item.update({"backing_device": src, "filesystem": fs, "uuid": uuid})
            except Exception as exc:  # noqa: BLE001
                item["probe_error"] = str(exc)
    # Fake fixtures can place values in commands/swap-details.json.  Real system
    # probing below remains read-only and bounded.
    fs = (item.get("filesystem") or "").lower()
    if fs == "btrfs":
        if "resume_offset" not in item and not data.get("fixture_name"):
            if not shutil.which("btrfs"):
                item["offset_error"] = "btrfs command not available; cannot map btrfs swap-file resume_offset"
            else:
                r = _run(["btrfs", "inspect-internal", "map-swapfile", "-r", path])
                if r.returncode == 0:
                    try:
                        item["resume_offset"] = parsers.parse_btrfs_map_swapfile_offset(r.stdout)
                    except Exception as exc:  # noqa: BLE001
                        item["offset_error"] = str(exc)
                else:
                    item["offset_error"] = (r.stderr or r.stdout or "btrfs map-swapfile failed").strip()
    elif fs == "ext4" or not fs:
        if "resume_offset" not in item and not data.get("fixture_name"):
            if shutil.which("filefrag"):
                r = _run(["filefrag", "-v", path])
                if r.returncode == 0:
                    try:
                        item["resume_offset"] = parsers.parse_filefrag_offset(r.stdout)
                        item["sparse"] = parsers.filefrag_output_has_holes(r.stdout)
                    except Exception as exc:  # noqa: BLE001
                        item["offset_error"] = str(exc)
                else:
                    item["offset_error"] = (r.stderr or r.stdout or "filefrag failed").strip()
            else:
                item["offset_error"] = "filefrag command not available"

    _apply_existing_resume_offset_fallback(path, item, data)


def _populate_partition_details(path: str, item: dict, data: dict) -> None:
    if not data.get("fixture_name") and shutil.which("blkid"):
        blk = _run(["blkid", "-o", "export", path])
        for ln in blk.stdout.splitlines():
            if "=" not in ln:
                continue
            k, v = ln.split("=", 1)
            if k == "UUID":
                item["uuid"] = v.lower()
            elif k == "PARTUUID":
                item["partuuid"] = v
            elif k == "TYPE":
                item["filesystem"] = v
    if not data.get("fixture_name") and shutil.which("lsblk"):
        lsblk = _run(["lsblk", "-no", "RM", path])
        item["removable"] = lsblk.stdout.strip() == "1"


def profile_from_probe_data(data: dict) -> SystemProfile:
    if "swap_details" not in data:
        data = dict(data)
        data["swap_details"] = probe_swap_details_from_data(data)
    devices = parse_swapon_show_bytes(data.get("swapon", ""))
    ram_bytes = int(data.get("ram_bytes") or 16 * 1024**3)
    candidates = classify_swap_targets(devices, ram_bytes, data.get("swap_details", {}))

    explicit_bootloader = data.get("bootloader")
    if explicit_bootloader in {"grub", "systemd-boot", "unknown"}:
        bootloader = explicit_bootloader
    elif data.get("grub_exists") and data.get("update_grub_exists"):
        bootloader = "grub"
    else:
        bootloader = "unknown"

    explicit_initramfs = data.get("initramfs")
    if explicit_initramfs in {"initramfs-tools", "dracut", "unknown"}:
        initramfs = explicit_initramfs
    elif data.get("initramfs_tools") and data.get("update_initramfs_exists", True):
        initramfs = "initramfs-tools"
    else:
        initramfs = "unknown"

    return SystemProfile(
        ram_bytes=ram_bytes,
        distro=data.get("distro", "Ubuntu"),
        distro_version=data.get("distro_version", "unknown"),
        kernel=data.get("kernel", "unknown"),
        power_state=data.get("power_state", ""),
        secure_boot=data.get("sb", data.get("secure_boot", "unknown")),
        lockdown=data.get("lockdown", "unknown"),
        bootloader=bootloader,
        initramfs=initramfs,
        timeshift_available=bool(data.get("timeshift_available", False)),
        cmdline=data.get("cmdline", ""),
        initramfs_resume=data.get("initramfs_resume", ""),
        fstab=data.get("fstab", ""),
        candidates=candidates,
        raw=data,
    )
