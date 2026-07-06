"""Hibernation configuration planner.

The default path uses already-active swap targets.  v0.42.12 keeps the
controlled swap-file sizing flow: the GUI may request creation/resizing of the
standard /swap.img file, and the GUI now exposes RAM-based slider marks while
the privileged helper still re-probes and validates that file before writing resume configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from ubuntu_hibernate_wizard.constants import (
    APP_VERSION, GRUB_FRAGMENT, MANAGED_SECTION_BEGIN,
    MANAGED_SECTION_END, PROTOCOL_VERSION, RESUME_FILE,
)
from ubuntu_hibernate_wizard.core.parsers import ParseError, parse_cmdline_resume, resume_uuid
from .swap_target_model import SwapTarget, SystemProfile, format_bytes_gib

GIB = 1024 ** 3
DEFAULT_SWAPFILE_PATH = "/swap.img"
FSTAB_FILE = "/etc/fstab"
MIN_SWAPFILE_BYTES = 1 * GIB
MAX_SWAPFILE_BYTES = 128 * GIB


@dataclass(slots=True)
class SwapFileRequest:
    """Request to create or resize the managed swap file before final validation."""

    path: str = DEFAULT_SWAPFILE_PATH
    size_bytes: int = 0
    mode: str = "create_or_resize"

    def __post_init__(self) -> None:
        self.path = validate_swapfile_request_path(self.path)
        self.size_bytes = validate_swapfile_request_size(self.size_bytes)
        if self.mode not in {"create_or_resize"}:
            raise ValueError("unsupported swap-file request mode")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "SwapFileRequest":
        if not isinstance(raw, dict):
            raise ValueError("swap_file_request must be an object")
        return cls(
            path=str(raw.get("path") or DEFAULT_SWAPFILE_PATH),
            size_bytes=int(raw.get("size_bytes") or 0),
            mode=str(raw.get("mode") or "create_or_resize"),
        )


def validate_swapfile_request_path(path: str) -> str:
    if path not in {"/swap.img", "/swapfile"}:
        raise ValueError("managed swap-file path must be /swap.img or /swapfile")
    return path


def validate_swapfile_request_size(size_bytes: int) -> int:
    try:
        size = int(size_bytes)
    except (TypeError, ValueError) as exc:
        raise ValueError("swap-file size must be an integer number of bytes") from exc
    if size < MIN_SWAPFILE_BYTES:
        raise ValueError("swap-file size must be at least 1 GiB")
    if size > MAX_SWAPFILE_BYTES:
        raise ValueError("swap-file size must not exceed 128 GiB")
    # Snap to MiB so helper-side truncation/fallocate stays predictable.
    mib = 1024 ** 2
    return (size // mib) * mib


def _normalised_ram_gib(ram_bytes: int) -> int:
    """Return RAM rounded to a whole GiB for user-facing swap suggestions."""
    return max(1, int(round(max(ram_bytes, 1) / GIB)))


def suggested_swap_sizes(ram_bytes: int) -> list[tuple[str, int]]:
    """Return the three GUI suggestion button sizes.

    The labels intentionally match the slider marks: minimum, recommended and
    2× RAM.  The minimum for hibernation is treated as RAM-sized swap; the
    recommendation adds a small margin for normal desktop workloads.
    """
    ram_gib = _normalised_ram_gib(ram_bytes)
    ram = ram_gib * GIB
    candidates = [
        ("Minimum", ram),
        ("Recommended", ram + 2 * GIB),
        ("2× RAM", 2 * ram),
    ]
    out: list[tuple[str, int]] = []
    seen: set[int] = set()
    for label, size in candidates:
        size = min(MAX_SWAPFILE_BYTES, max(MIN_SWAPFILE_BYTES, validate_swapfile_request_size(size)))
        if size not in seen:
            out.append((label, size))
            seen.add(size)
    while len(out) < 3:
        size = min(MAX_SWAPFILE_BYTES, (len(out) + 1) * ram)
        size = validate_swapfile_request_size(size)
        if size not in seen:
            out.append((f"Option {len(out)+1}", size))
            seen.add(size)
        else:
            out.append((f"Option {len(out)+1}", min(MAX_SWAPFILE_BYTES, size + GIB)))
    return out[:3]


def swapfile_slider_marks(ram_bytes: int) -> list[tuple[str, int]]:
    """Return labelled GiB marks for the managed swap-file size slider."""
    marks: list[tuple[str, int]] = []
    seen: set[int] = set()
    for label, size in suggested_swap_sizes(ram_bytes):
        gib = max(1, int(round(size / GIB)))
        if gib not in seen:
            marks.append((label, gib))
            seen.add(gib)
    return marks


@dataclass(slots=True)
class PlannedStep:
    id: str
    title: str
    detail: str = ""
    destructive: bool = False


@dataclass(slots=True)
class ModificationPlan:
    selected_target: SwapTarget
    steps: list[PlannedStep]
    planned_files: list[str]
    warnings: list[str] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    swap_file_request: SwapFileRequest | None = None

    @property
    def can_apply(self) -> bool:
        if self.blocking_reasons:
            return False
        if self.swap_file_request is not None:
            return True
        return self.selected_target.selectable

    def to_helper_request(self, *, dry_run: bool = False) -> dict:
        req = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ-uhw"),
            "action": "apply-plan",
            "dry_run": bool(dry_run),
            "app_version": APP_VERSION,
            "selected_target": self.selected_target.to_dict(),
            "rollback": {"mode": "timeshift_or_file_backup", "timeshift_allowed": True},
            "planned_files": list(self.planned_files),
            "steps": [s.id for s in self.steps],
        }
        if self.swap_file_request is not None:
            req["swap_file_request"] = self.swap_file_request.to_dict()
        return req


def build_modification_plan(profile: SystemProfile, target: SwapTarget) -> ModificationPlan:
    """Build a human/machine readable plan from a selected existing target."""
    warnings = list(target.warnings)
    blockers = list(profile.blocking_reasons)
    if target.blocked:
        blockers.extend(target.reasons or ["Selected swap target is blocked"])
    if target.status == "warning_option":
        blockers.append("Selected target is not valid for automatic apply")
    blockers.extend(conflict_warnings(profile, target))

    steps = [
        PlannedStep("validate_target", "Re-check selected hibernation target", _target_summary(target)),
        PlannedStep("create_rollback", "Create rollback snapshot before file writes", "File backup manifest is stored under /var/lib or /var/backups/ubuntu-hibernate-wizard"),
        PlannedStep("write_resume_config", f"Write {RESUME_FILE}", generated_resume_config(target).strip()),
        PlannedStep("write_grub_config", f"Write {GRUB_FRAGMENT}", "Managed GRUB fragment; /etc/default/grub is not rewritten"),
        PlannedStep("update_initramfs", "Run update-initramfs -u", "Regenerate initramfs for current Ubuntu initramfs-tools stack"),
        PlannedStep("update_grub", "Run update-grub", "Regenerate GRUB configuration from managed fragment"),
    ]
    return ModificationPlan(target, steps, [RESUME_FILE, GRUB_FRAGMENT], warnings, _dedupe(blockers))


def build_swapfile_modification_plan(profile: SystemProfile, request: SwapFileRequest) -> ModificationPlan:
    """Build a plan that first creates/resizes /swap.img, then validates it live."""
    blockers = list(profile.blocking_reasons)
    # Existing-swap absence must not block the create/resize path; the whole
    # purpose of this plan is to make a valid disk swap target.
    blockers = [b for b in blockers if b != "No existing active disk swap target is usable for hibernation"]
    if profile.raw.get("read_only_config"):
        # Keep the explicit read-only blocker.
        pass
    if profile.bootloader != "grub" or profile.initramfs != "initramfs-tools" or not profile.has_hibernate_kernel_support:
        pass
    placeholder = SwapTarget(
        id="managed-swapfile-request",
        kind="file",
        path=request.path,
        size_bytes=request.size_bytes,
        active=False,
        status="valid_option",
        title=f"Prepare {request.path}",
        detail=f"Create or resize managed swap file to {format_bytes_gib(request.size_bytes)}; final UUID and offset are detected after creation",
        filesystem="ext4",
    )
    steps = [
        PlannedStep("create_rollback", "Create rollback snapshot before swap/file writes", "Rollback metadata is created before changing swap or boot configuration"),
        PlannedStep("ensure_swap_file", f"Create or resize {request.path}", f"Target size {format_bytes_gib(request.size_bytes)}; activate it as swap and ensure /etc/fstab entry", destructive=True),
        PlannedStep("validate_target", "Re-check new swap-file hibernation target", "Detect filesystem UUID and resume_offset after the swap file is active"),
        PlannedStep("write_resume_config", f"Write {RESUME_FILE}", "Generated after live resume_offset validation"),
        PlannedStep("write_grub_config", f"Write {GRUB_FRAGMENT}", "Managed GRUB fragment; /etc/default/grub is not rewritten"),
        PlannedStep("update_initramfs", "Run update-initramfs -u", "Regenerate initramfs for current Ubuntu initramfs-tools stack"),
        PlannedStep("update_grub", "Run update-grub", "Regenerate GRUB configuration from managed fragment"),
    ]
    warnings = [
        "Swap-file creation/resizing changes disk usage and may briefly switch swap state; review carefully before applying.",
        "The helper will accept only /swap.img or /swapfile on a supported local filesystem and will re-probe before writing resume config.",
    ]
    return ModificationPlan(placeholder, steps, [RESUME_FILE, GRUB_FRAGMENT, FSTAB_FILE], warnings, _dedupe(blockers), request)


def generated_resume_config(target: SwapTarget) -> str:
    if not target.uuid:
        raise ValueError("target UUID is required")
    if target.kind == "file":
        if not target.resume_offset:
            raise ValueError("swap-file target requires resume_offset")
        return f"RESUME=UUID={target.uuid} resume_offset={target.resume_offset}\n"
    return f"RESUME=UUID={target.uuid}\n"


def generated_grub_fragment(target: SwapTarget) -> str:
    """Return an idempotent GRUB default fragment for the resume target."""
    if not target.uuid:
        raise ValueError("target UUID is required")
    params = [f"resume=UUID={target.uuid}"]
    if target.kind == "file":
        if not target.resume_offset:
            raise ValueError("swap-file target requires resume_offset")
        params.append(f"resume_offset={target.resume_offset}")
    add_lines = "".join(f'uhw_add_kernel_param "{param}"\n' for param in params)
    return (
        f"{MANAGED_SECTION_BEGIN}\n"
        "# Managed by Ubuntu Hibernate Wizard. Manual edits inside this block may be overwritten.\n"
        'uhw_add_kernel_param() {\n'
        '  case " ${GRUB_CMDLINE_LINUX_DEFAULT} " in\n'
        '    *" $1 "*) ;;\n'
        '    *) GRUB_CMDLINE_LINUX_DEFAULT="${GRUB_CMDLINE_LINUX_DEFAULT} $1" ;;\n'
        '  esac\n'
        '}\n'
        f"{add_lines}"
        "unset -f uhw_add_kernel_param\n"
        f"{MANAGED_SECTION_END}\n"
    )


def conflict_warnings(profile: SystemProfile, target: SwapTarget) -> list[str]:
    warnings: list[str] = []
    try:
        params = parse_cmdline_resume(profile.cmdline or "")
    except ParseError as exc:
        warnings.append(f"Cannot parse existing kernel command line: {exc}")
        return warnings
    kuuid = resume_uuid(params)
    if kuuid and target.uuid and kuuid.lower() != target.uuid.lower():
        warnings.append(f"Existing kernel resume UUID {kuuid} differs from selected target {target.uuid}")
    if params.resume_offset is not None:
        expected = target.resume_offset if target.kind == "file" else None
        if expected is None:
            warnings.append("Existing kernel resume_offset is present but selected target is a swap partition")
        elif params.resume_offset != expected:
            warnings.append(f"Existing kernel resume_offset {params.resume_offset} differs from selected target {expected}")
    init_line = (profile.initramfs_resume or "").strip()
    if init_line:
        expected = generated_resume_config(target).strip()
        if init_line != expected and ("RESUME=" in init_line or "resume_offset" in init_line):
            warnings.append("Existing initramfs resume configuration differs from the selected target")
    return _dedupe(warnings)


def _target_summary(target: SwapTarget) -> str:
    if target.kind == "file":
        return f"{target.path}, {format_bytes_gib(target.size_bytes)}, filesystem {target.filesystem}, offset {target.resume_offset}"
    return f"{target.path}, {format_bytes_gib(target.size_bytes)}, UUID {target.uuid}"


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out
