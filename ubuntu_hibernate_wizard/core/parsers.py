"""Safety-critical parsers. All input is text captured with LC_ALL=C (§20.8).

Every parser rejects invalid input loudly (§20.4): no silent fallbacks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class ParseError(ValueError):
    """Raised when system command output cannot be parsed safely."""


# ---------------------------------------------------------------- filefrag
_FIRST_EXTENT = re.compile(r"^\s*0:\s+\d+\.\.\s*\d+:\s+(\d+)[.:\s]")


def parse_filefrag_offset(output: str) -> int:
    """Extract the physical offset of the first extent from `filefrag -v`.

    Accepts `5986304..`, `5986304:` and `5986304 ` field styles (§20.4).
    Never falls back to an old value: raises ParseError instead.
    """
    for line in output.splitlines():
        m = _FIRST_EXTENT.match(line)
        if m:
            offset = int(m.group(1))
            if offset <= 0:
                raise ParseError(f"non-positive filefrag offset: {offset}")
            return offset
    raise ParseError("no valid first extent line found in filefrag output")


# ---------------------------------------------------------------- swapon
@dataclass
class SwapDevice:
    name: str
    type: str  # "file" | "partition"
    size_bytes: int
    used_bytes: int
    priority: int

    @property
    def is_zram(self) -> bool:
        return self.name.startswith("/dev/zram")


def parse_swapon_show_bytes(output: str) -> list[SwapDevice]:
    """Parse `swapon --show --bytes` (LC_ALL=C)."""
    devices: list[SwapDevice] = []
    lines = [ln for ln in output.splitlines() if ln.strip()]
    if not lines:
        return devices
    if not lines[0].upper().startswith("NAME"):
        raise ParseError("unexpected swapon header: " + lines[0][:60])
    for ln in lines[1:]:
        parts = ln.split()
        if len(parts) < 5:
            raise ParseError("short swapon row: " + ln[:60])
        try:
            devices.append(SwapDevice(
                name=parts[0], type=parts[1],
                size_bytes=int(parts[2]), used_bytes=int(parts[3]),
                priority=int(parts[4]),
            ))
        except ValueError as e:
            raise ParseError(f"bad swapon row {ln!r}: {e}") from e
    return devices


# ---------------------------------------------------------------- findmnt
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
                      r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def validate_uuid(uuid: str) -> str:
    if not _UUID_RE.match(uuid or ""):
        raise ParseError(f"invalid filesystem UUID: {uuid!r}")
    return uuid.lower()


def parse_findmnt_target(output: str) -> tuple[str, str, str]:
    """Parse `findmnt -no SOURCE,FSTYPE,UUID -T <path>` -> (source, fstype, uuid)."""
    line = output.strip().splitlines()[0] if output.strip() else ""
    parts = line.split()
    if len(parts) != 3:
        raise ParseError("unexpected findmnt output: " + line[:80])
    source, fstype, uuid = parts
    return source, fstype, validate_uuid(uuid)


# ---------------------------------------------------------------- cmdline
@dataclass
class ResumeParams:
    resume: str | None = None          # e.g. "UUID=..." or "/dev/sda2"
    resume_offset: int | None = None
    noresume: bool = False
    raw_tokens: list[str] = field(default_factory=list)


def parse_cmdline_resume(cmdline: str) -> ResumeParams:
    """Extract resume-related parameters from /proc/cmdline."""
    p = ResumeParams(raw_tokens=cmdline.split())
    for tok in p.raw_tokens:
        if tok == "noresume":
            p.noresume = True
        elif tok.startswith("resume_offset="):
            val = tok.split("=", 1)[1]
            if not val.isdigit() or int(val) <= 0:
                raise ParseError(f"invalid resume_offset token: {tok!r}")
            p.resume_offset = int(val)
        elif tok.startswith("resume="):
            p.resume = tok.split("=", 1)[1]
    return p


def resume_uuid(params: ResumeParams) -> str | None:
    """Return the UUID part of resume=UUID=..., else None."""
    if params.resume and params.resume.upper().startswith("UUID="):
        return params.resume.split("=", 1)[1].lower()
    return None
