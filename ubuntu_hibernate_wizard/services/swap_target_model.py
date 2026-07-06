"""Pure model objects for v0.42 hibernation target selection.

v0.42 deliberately supports existing active disk swap targets only.  It never
creates, resizes, formats, repartitions, or enables swap storage.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

TargetKind = Literal["partition", "file", "swapfile", "zram", "unknown"]
TargetStatus = Literal["recommended", "valid_option", "warning_option", "blocked"]


@dataclass(slots=True)
class SwapTarget:
    """A classified swap target candidate."""

    id: str
    kind: TargetKind
    path: str
    size_bytes: int
    used_bytes: int = 0
    priority: int = 0
    active: bool = True
    status: TargetStatus = "blocked"
    title: str = ""
    detail: str = ""
    uuid: str | None = None
    partuuid: str | None = None
    filesystem: str | None = None
    backing_device: str | None = None
    resume_offset: int | None = None
    removable: bool = False
    encrypted: bool = False
    encryption_stable: bool | None = None
    classification: str = "unknown"
    encryption_source: list[str] = field(default_factory=list)
    crypttab_name: str | None = None
    crypttab_options: list[str] = field(default_factory=list)
    mapper_name: str | None = None
    mapper_is_crypt: bool | None = None
    parent_device: str | None = None
    stable_resume_id: str | None = None
    sparse: bool = False
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def selectable(self) -> bool:
        return self.status in {"recommended", "valid_option"}

    @property
    def blocked(self) -> bool:
        return self.status == "blocked"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "SwapTarget":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in raw.items() if k in known})


def format_bytes_gib(size_bytes: int) -> str:
    return f"{size_bytes / (1024 ** 3):.1f} GiB"


@dataclass(slots=True)
class SystemProfile:
    """Facts used by the GUI and planner.

    The profile can come from real system probing or from a test fixture loaded
    through --fake-system.
    """

    ram_bytes: int
    distro: str = "Ubuntu"
    distro_version: str = "unknown"
    kernel: str = "unknown"
    power_state: str = ""
    secure_boot: str = "unknown"
    lockdown: str = "unknown"
    bootloader: str = "unknown"
    initramfs: str = "unknown"
    timeshift_available: bool = False
    cmdline: str = ""
    initramfs_resume: str = ""
    fstab: str = ""
    candidates: list[SwapTarget] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def has_hibernate_kernel_support(self) -> bool:
        return "disk" in self.power_state.split()

    @property
    def supported_boot_stack(self) -> bool:
        return self.bootloader == "grub" and self.initramfs == "initramfs-tools"

    @property
    def recommended_target(self) -> SwapTarget | None:
        for target in self.candidates:
            if target.status == "recommended":
                return target
        for target in self.candidates:
            if target.selectable:
                return target
        return None

    @property
    def blocking_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not self.has_hibernate_kernel_support:
            reasons.append("Kernel does not advertise hibernate support in /sys/power/state")
        if self.bootloader != "grub":
            reasons.append("v0.42 supports GRUB boot systems only")
        if self.initramfs != "initramfs-tools":
            reasons.append("v0.42 supports initramfs-tools only")
        if self.recommended_target is None:
            reasons.append("No existing active disk swap target is usable for hibernation")
        if self.raw.get("read_only_config"):
            reasons.append("Configuration filesystem is marked read-only; automatic apply is blocked until writable /etc and boot configuration paths are available")
        return reasons

    def to_dict(self) -> dict:
        d = asdict(self)
        d["candidates"] = [c.to_dict() for c in self.candidates]
        return d

    @classmethod
    def from_dict(cls, raw: dict) -> "SystemProfile":
        raw = dict(raw)
        raw["candidates"] = [SwapTarget.from_dict(c) for c in raw.get("candidates", [])]
        return cls(**raw)
