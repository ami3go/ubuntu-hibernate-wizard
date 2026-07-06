"""Support diagnostic export with explicit redaction.

The report intentionally includes only wizard-relevant facts.  It does not dump
unrelated system files or recurse through the home directory.  Public-facing
export is a structured ZIP bundle; the text summary is retained inside it.
"""
from __future__ import annotations

import json
from dataclasses import asdict
import os
import re
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ubuntu_hibernate_wizard.constants import APP_NAME, APP_VERSION

_HOME_RE = re.compile(r"/home/[^/\s]+")
_HOST_RE = re.compile(r"\b(hostname|Host):\s*[^\s]+", re.IGNORECASE)
_MACHINE_ID_RE = re.compile(r"(?im)^.*(?:/etc/)?machine-id\s*[:=].*$")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)
_TOKEN_RE = re.compile(r"(?i)\b(api[_-]?key|api[_-]?token|token|secret|password)\s*[:=]\s*[^\s,;]+")
_SERIAL_RE = re.compile(r"(?i)\b(serial|disk serial)\s*[:=]\s*[^\s,;]+")
_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


def redact_diagnostic_text(text: str, *, redact_uuids: bool = False) -> str:
    """Apply the public diagnostic ZIP redaction policy.

    UUIDs are useful for troubleshooting, but they are also machine-identifying.
    Public ZIP exports redact them by default; internal callers may opt out only
    when the user explicitly needs exact identifiers for private support.
    """
    text = _PRIVATE_KEY_RE.sub("<redacted-private-key>", text or "")
    text = _MACHINE_ID_RE.sub("machine-id: <redacted>", text)
    text = _HOME_RE.sub("/home/<user>", text)
    text = _HOST_RE.sub(lambda m: m.group(1) + ": <redacted>", text)
    text = _TOKEN_RE.sub(lambda m: m.group(1) + "=<redacted>", text)
    text = _SERIAL_RE.sub(lambda m: m.group(1) + ": <redacted>", text)
    if redact_uuids:
        text = _UUID_RE.sub("<redacted-uuid>", text)
    return text


def _safe_json(data: Any, *, redact_uuids: bool = False) -> str:
    return redact_diagnostic_text(json.dumps(data, indent=2, sort_keys=True, default=str), redact_uuids=redact_uuids)


def _write_zip_text(zf: zipfile.ZipFile, name: str, text: str, *, redact_uuids: bool = False) -> None:
    zf.writestr(name, redact_diagnostic_text(text or "", redact_uuids=redact_uuids))


def build_fixture_diagnostic_summary(profile) -> str:
    """Return the deterministic short summary used by fake-system golden tests."""
    fixture = (profile.raw or {}).get("fixture_name") or "unknown"
    recommended = profile.recommended_target.path if profile.recommended_target else "none"
    blockers = " | ".join(profile.blocking_reasons) if profile.blocking_reasons else "none"
    classifications = ", ".join(c.classification for c in profile.candidates)
    return (
        f"fixture={fixture}\n"
        f"targets={len(profile.candidates)}\n"
        f"recommended={recommended}\n"
        f"blockers={blockers}\n"
        f"classifications={classifications}\n"
    )


def build_diagnostic_report(profile, plan=None, verify=None, *, redact_uuids: bool = False) -> str:
    """Build a redacted user-shareable text summary."""
    lines: list[str] = []
    lines.append("Ubuntu Hibernate Wizard diagnostic summary")
    lines.append("Generated: " + datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    lines.append("")
    lines.append("Scope: v0.42.12 existing swap target or managed /swap.img create/resize")
    lines.append("Supported boot stack: GRUB + initramfs-tools")
    lines.append("")
    lines.append("System summary")
    lines.append(f"- Distro: {profile.distro_version or profile.distro}")
    lines.append(f"- Kernel: {profile.kernel}")
    lines.append(f"- Bootloader: {profile.bootloader}")
    lines.append(f"- Initramfs: {profile.initramfs}")
    lines.append(f"- Secure Boot: {profile.secure_boot}")
    lines.append(f"- Kernel power states: {profile.power_state.strip()}")
    lines.append("")
    lines.append("Swap candidates")
    for c in profile.candidates:
        lines.append(
            f"- {c.path} [{c.kind}] classification={c.classification} status={c.status} "
            f"size={c.size_bytes} uuid={c.uuid} offset={c.resume_offset} encrypted={c.encrypted}"
        )
        for w in c.warnings:
            lines.append(f"  warning: {w}")
        for r in c.reasons:
            lines.append(f"  reason: {r}")
    if not profile.candidates:
        lines.append("- none")
    lines.append("")
    lines.append("Blocking reasons")
    for r in profile.blocking_reasons:
        lines.append(f"- {r}")
    if not profile.blocking_reasons:
        lines.append("- none")
    if plan is not None:
        lines.append("")
        lines.append("Current plan")
        lines.append(_safe_json({
            "selected_target": plan.selected_target.to_dict(),
            "planned_files": plan.planned_files,
            "steps": [s.id for s in plan.steps],
            "warnings": plan.warnings,
            "blocking_reasons": plan.blocking_reasons,
        }, redact_uuids=redact_uuids))
    if verify is not None:
        lines.append("")
        lines.append("Last verification")
        lines.append(_safe_json(verify, redact_uuids=redact_uuids))
    lines.append("")
    lines.append("Raw probe excerpt")
    raw = dict(profile.raw or {})
    # Avoid dumping full unrelated /etc/fstab. Keep redacted bounded snapshots in
    # the ZIP configs/ directory instead.
    raw.pop("fstab", None)
    raw.pop("crypttab", None)
    raw.pop("grub_default", None)
    raw["config_snapshots"] = "redacted snapshots are included under configs/ where available"
    lines.append(_safe_json(raw, redact_uuids=redact_uuids))
    return redact_diagnostic_text("\n".join(lines) + "\n", redact_uuids=redact_uuids)


def build_diagnostic_manifest(profile, files: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "platform": {
            "distro": profile.distro,
            "distro_version": profile.distro_version,
            "kernel": profile.kernel,
            "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "unknown"),
        },
        "diagnostic_files": files,
        "redaction": {
            "enabled": True,
            "notes": [
                "User paths and hostnames are redacted where practical.",
                "machine-id, private keys, tokens and unrelated home-directory files are not included.",
                "Filesystem and swap UUIDs are redacted in public diagnostic ZIP exports by default.",
            ],
        },
    }


def _swap_detection_json(profile) -> dict[str, Any]:
    return {
        "ram_bytes": profile.ram_bytes,
        "blocking_reasons": profile.blocking_reasons,
        "targets": [c.to_dict() for c in profile.candidates],
    }


def _plan_json(plan) -> dict[str, Any]:
    if plan is None:
        return {"available": False}
    return {
        "available": True,
        "selected_target": plan.selected_target.to_dict(),
        "planned_files": plan.planned_files,
        "steps": [asdict(step) for step in plan.steps],
        "warnings": plan.warnings,
        "blocking_reasons": plan.blocking_reasons,
        "can_apply": plan.can_apply,
    }


def write_diagnostic_zip(path: str | Path, profile, plan=None, verify=None, *, redact_uuids: bool = True) -> Path:
    """Write a structured, redacted diagnostic ZIP bundle."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, str]] = []

    def add_file(name: str, description: str) -> None:
        files.append({"path": name, "description": description})

    summary = build_diagnostic_report(profile, plan, verify, redact_uuids=redact_uuids)
    fixture_summary = build_fixture_diagnostic_summary(profile)
    swap_json = _safe_json(_swap_detection_json(profile), redact_uuids=redact_uuids)
    plan_json = _safe_json(_plan_json(plan), redact_uuids=redact_uuids)
    verify_json = _safe_json(verify or {"available": False}, redact_uuids=redact_uuids)
    raw = dict(profile.raw or {})

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        add_file("summary.txt", "Human-readable diagnostic summary")
        _write_zip_text(zf, "summary.txt", summary, redact_uuids=redact_uuids)
        if (profile.raw or {}).get("fixture_name"):
            add_file("fixture-summary.txt", "Deterministic fake-system summary used by golden tests")
            _write_zip_text(zf, "fixture-summary.txt", fixture_summary, redact_uuids=False)
        add_file("swap-detection.json", "Structured swap target detection result")
        _write_zip_text(zf, "swap-detection.json", swap_json, redact_uuids=redact_uuids)
        add_file("swap-detection.txt", "Readable swap target detection result")
        _write_zip_text(zf, "swap-detection.txt", summary, redact_uuids=redact_uuids)
        add_file("app.log", "Application-side diagnostic event log excerpt")
        _write_zip_text(zf, "app.log", raw.get("app_log", "No application log was attached to this export.\n"), redact_uuids=redact_uuids)
        add_file("system-info.txt", "Bounded operating-system and kernel summary")
        _write_zip_text(zf, "system-info.txt", "\n".join([
            f"Distro: {profile.distro_version or profile.distro}",
            f"Kernel: {profile.kernel}",
            f"Bootloader: {profile.bootloader}",
            f"Initramfs: {profile.initramfs}",
            f"Power states: {profile.power_state.strip()}",
        ]) + "\n", redact_uuids=redact_uuids)
        for name, key, desc in [
            ("commands/proc-swaps.txt", "proc_swaps", "Captured /proc/swaps output"),
            ("commands/proc-meminfo.txt", "proc_meminfo", "Captured /proc/meminfo excerpt when available"),
            ("commands/lsblk.json", "lsblk_json", "lsblk JSON output"),
            ("commands/swapon-show.txt", "swapon", "swapon --show --bytes output"),
            ("commands/findmnt.json", "findmnt_json", "findmnt JSON output when available"),
            ("commands/dmsetup-info.txt", "dmsetup_info", "dmsetup mapper summary when available"),
        ]:
            add_file(name, desc)
            _write_zip_text(zf, name, raw.get(key, ""), redact_uuids=redact_uuids)
        for name, key, desc in [
            ("configs/fstab.redacted.txt", "fstab", "Redacted fstab snapshot"),
            ("configs/crypttab.redacted.txt", "crypttab", "Redacted crypttab snapshot"),
            ("configs/grub.redacted.txt", "grub_default", "Redacted /etc/default/grub snapshot"),
        ]:
            add_file(name, desc)
            _write_zip_text(zf, name, raw.get(key, ""), redact_uuids=redact_uuids)
        add_file("rollback/rollback-plan.json", "Current rollback/plan context if available")
        _write_zip_text(zf, "rollback/rollback-plan.json", plan_json, redact_uuids=redact_uuids)
        add_file("rollback/rollback-summary.txt", "Readable rollback/plan context")
        _write_zip_text(zf, "rollback/rollback-summary.txt", "Plan available: " + ("yes" if plan is not None else "no") + "\n", redact_uuids=redact_uuids)
        add_file("ui/wizard-state.json", "Current wizard-side verification state")
        _write_zip_text(zf, "ui/wizard-state.json", verify_json, redact_uuids=redact_uuids)
        manifest = build_diagnostic_manifest(profile, files)
        zf.writestr("manifest.json", _safe_json(manifest, redact_uuids=redact_uuids))

    try:
        out.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return out
