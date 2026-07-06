"""Swap target classifier for Ubuntu Hibernate Wizard v0.42.

The classifier follows the v0.42 decision table: existing active disk swap
partition/file targets only; zram and unsupported or undersized targets are not
selectable.  It is pure and fixture-friendly.
"""
from __future__ import annotations

from .swap_target_model import SwapTarget, format_bytes_gib
from ubuntu_hibernate_wizard.core.parsers import SwapDevice

SUPPORTED_FILE_SYSTEMS = {"ext4", "btrfs"}


def classify_swap_targets(
    devices: list[SwapDevice],
    ram_bytes: int,
    details: dict[str, dict] | None = None,
) -> list[SwapTarget]:
    """Return classified swap targets from swapon rows and probe details.

    details is keyed by swap path and may contain uuid, fstype/filesystem,
    source/backing_device, resume_offset, sparse, removable, encrypted,
    encryption_stable, active.
    """
    details = details or {}
    candidates: list[SwapTarget] = []

    for dev in devices:
        info = dict(details.get(dev.name, {}))
        dtype = (dev.type or "unknown").lower()
        kind = "zram" if dev.is_zram else ("file" if dtype == "file" else "partition" if dtype == "partition" else "unknown")
        t = SwapTarget(
            id=dev.name,
            kind=kind,
            path=dev.name,
            size_bytes=dev.size_bytes,
            used_bytes=dev.used_bytes,
            priority=dev.priority,
            active=bool(info.get("active", True)),
            uuid=info.get("uuid"),
            partuuid=info.get("partuuid"),
            filesystem=info.get("filesystem") or info.get("fstype"),
            backing_device=info.get("backing_device") or info.get("source"),
            resume_offset=info.get("resume_offset"),
            removable=bool(info.get("removable", False)),
            encrypted=bool(info.get("encrypted", False)),
            encryption_stable=info.get("encryption_stable"),
            classification=info.get("classification") or ("zram" if dev.is_zram else "plain_swapfile" if dtype == "file" else "plain_swap_partition" if dtype == "partition" else "unknown"),
            encryption_source=list(info.get("encryption_source") or []),
            crypttab_name=info.get("crypttab_name"),
            crypttab_options=list(info.get("crypttab_options") or []),
            mapper_name=info.get("mapper_name"),
            mapper_is_crypt=info.get("mapper_is_crypt"),
            parent_device=info.get("parent_device"),
            stable_resume_id=info.get("stable_resume_id") or info.get("uuid") or info.get("partuuid"),
            sparse=bool(info.get("sparse", False)),
        )
        t.title = _title(t)
        # Preserve detector-provided warnings/blockers before applying generic
        # v0.42 target validation.
        t.warnings.extend(info.get("warnings") or [])
        t.reasons.extend(info.get("blockers") or [])
        _classify_one(t, ram_bytes)
        candidates.append(t)

    _choose_recommended(candidates)
    return candidates


def _title(t: SwapTarget) -> str:
    if t.kind == "partition":
        return f"Swap partition {t.path}"
    if t.kind == "file":
        return f"Swap file {t.path}"
    if t.kind == "zram":
        return f"zram swap {t.path}"
    return f"Swap target {t.path}"


def _classify_one(t: SwapTarget, ram_bytes: int) -> None:
    size = format_bytes_gib(t.size_bytes)
    ram = format_bytes_gib(ram_bytes)
    t.detail = f"{size} swap, detected RAM {ram}"

    if t.kind == "zram":
        t.status = "blocked"
        t.reasons.append("zram is volatile RAM compression and cannot store a hibernation image across power-off")
        return

    if not t.active:
        t.status = "warning_option"
        t.warnings.append("Detected but not active; v0.42 does not enable inactive swap")
        return

    if t.removable:
        t.status = "blocked"
        t.reasons.append("Swap on removable media is not safe as a resume target")
        return

    if t.size_bytes < ram_bytes:
        t.status = "warning_option"
        t.warnings.append("Swap target is smaller than RAM; v0.42 blocks apply by default")
        return

    if t.kind == "partition":
        if t.encrypted or t.classification in {"encrypted_random_key_swap", "encrypted_swap_crypttab", "encrypted_persistent_swap", "unknown_mapper_swap"}:
            t.status = "blocked"
            if t.classification == "encrypted_random_key_swap":
                t.reasons.append("Encrypted swap uses a random key/swap crypttab setup and cannot be used as a resume target")
            elif t.classification == "unknown_mapper_swap":
                t.reasons.append("Mapper swap backing cannot be proven safe for resume")
            else:
                t.reasons.append("Encrypted swap is blocked unless a stable initramfs resume path is explicitly implemented and tested")
            return
        if not t.uuid:
            t.status = "blocked"
            t.reasons.append("No stable UUID was detected for this partition")
            return
        t.status = "valid_option"
        if t.encrypted:
            t.warnings.append("Encrypted swap mapping is marked stable and must be available during initramfs resume")
        return

    if t.kind == "file":
        if t.encrypted or t.classification in {"encrypted_random_key_swap", "encrypted_swap_crypttab", "encrypted_persistent_swap", "unknown_mapper_swap"}:
            t.status = "blocked"
            if t.classification == "unknown_mapper_swap":
                t.reasons.append("Mapper swap backing cannot be proven safe for resume")
            else:
                t.reasons.append("Encrypted swap is blocked unless a stable initramfs resume path is explicitly implemented and tested")
            return
        fs = (t.filesystem or "").lower()
        if fs not in SUPPORTED_FILE_SYSTEMS:
            t.status = "blocked"
            t.reasons.append(f"Unsupported swap-file filesystem: {t.filesystem or 'unknown'}")
            return
        if t.sparse:
            t.status = "blocked"
            t.reasons.append("Swap file appears sparse or has holes; resume location is not reliable")
            return
        if not t.uuid:
            t.status = "blocked"
            t.reasons.append("No backing filesystem UUID was detected")
            return
        if not isinstance(t.resume_offset, int) or t.resume_offset <= 0:
            t.status = "blocked"
            if fs == "btrfs":
                t.reasons.append("btrfs swap-file resume offset must come from btrfs inspect-internal map-swapfile -r")
            else:
                t.reasons.append("Swap-file resume offset could not be detected reliably")
            return
        t.status = "valid_option"
        return

    t.status = "blocked"
    t.reasons.append("Unknown swap target type")


def _choose_recommended(candidates: list[SwapTarget]) -> None:
    selectable_partitions = [c for c in candidates if c.kind == "partition" and c.status == "valid_option"]
    selectable_files = [c for c in candidates if c.kind == "file" and c.status == "valid_option"]
    chosen = None
    if selectable_partitions:
        chosen = max(selectable_partitions, key=lambda c: c.size_bytes)
    elif selectable_files:
        chosen = max(selectable_files, key=lambda c: c.size_bytes)
    if chosen:
        chosen.status = "recommended"
