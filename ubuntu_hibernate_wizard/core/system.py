"""fstab editing (§6 Step 6), verification (§24), resize journal (§26.2),
backup manifest (§9). Pure logic + explicit small I/O helpers."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field

from .parsers import (ParseError, parse_cmdline_resume, resume_uuid,
                      validate_uuid)

# ---------------------------------------------------------------- fstab
def ensure_swap_entry(fstab_text: str, swap_path: str) -> tuple[str, bool]:
    """Ensure exactly one active swap entry for swap_path.

    Returns (new_text, changed). Never duplicates entries (§12.9).
    """
    entry = f"{swap_path} none swap sw 0 0"
    for line in fstab_text.splitlines():
        s = line.strip()
        if s.startswith("#") or not s:
            continue
        fields = s.split()
        if len(fields) >= 3 and fields[0] == swap_path and fields[2] == "swap":
            return fstab_text, False  # already present
    new = fstab_text
    if new and not new.endswith("\n"):
        new += "\n"
    new += entry + "\n"
    return new, True


# ---------------------------------------------------------------- verification
@dataclass
class VerificationResult:
    active_swap_ok: bool
    resume_uuid_ok: bool
    resume_offset_ok: bool
    initramfs_resume_ok: bool
    errors: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return (self.active_swap_ok and self.resume_uuid_ok
                and self.resume_offset_ok and self.initramfs_resume_ok)


def verify(swap_path: str, active_swaps: list[str], fs_uuid: str,
           real_offset: int | None, cmdline: str, initramfs_resume: str,
           *, target_kind: str = "file") -> VerificationResult:
    """Compare reality vs kernel vs initramfs (§24, §22 fixture)."""
    errors: list[str] = []
    fs_uuid = validate_uuid(fs_uuid)

    swap_ok = swap_path in active_swaps
    if not swap_ok:
        errors.append(f"{swap_path} is not an active swap device")

    try:
        params = parse_cmdline_resume(cmdline)
    except ParseError as e:
        return VerificationResult(swap_ok, False, False, False, [str(e)])

    kuuid = resume_uuid(params)
    uuid_ok = kuuid == fs_uuid
    if not uuid_ok:
        errors.append(f"kernel resume UUID {kuuid} != filesystem UUID {fs_uuid}")

    if target_kind == "partition":
        offset_ok = params.resume_offset is None
        if not offset_ok:
            errors.append("kernel resume_offset is present for a swap partition target")
    else:
        offset_ok = params.resume_offset == real_offset
        if not offset_ok:
            errors.append(f"kernel resume_offset {params.resume_offset} "
                          f"!= real offset {real_offset}")

    init_lower = initramfs_resume.lower()
    if target_kind == "partition":
        init_ok = f"uuid={fs_uuid}" in init_lower and "resume_offset" not in init_lower
    else:
        init_ok = (f"uuid={fs_uuid}" in init_lower
                   and f"resume_offset={real_offset}" in init_lower)
    if not init_ok:
        errors.append("initramfs resume config does not match selected target")

    return VerificationResult(swap_ok, uuid_ok, offset_ok, init_ok, errors)


# ---------------------------------------------------------------- resize journal (§26.2)
JOURNAL_PATH = "/var/lib/ubuntu-hibernate-wizard/resize-journal.json"
PHASES = ("building", "switching", "activated")


@dataclass
class ResizeJournal:
    target: str
    side: str
    size_bytes: int
    phase: str
    updated_at: float = 0.0

    def save(self, path: str = JOURNAL_PATH) -> None:
        if self.phase not in PHASES:
            raise ValueError(f"bad phase {self.phase}")
        self.updated_at = time.time()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(asdict(self), f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    @staticmethod
    def load(path: str = JOURNAL_PATH) -> "ResizeJournal | None":
        try:
            with open(path) as f:
                d = json.load(f)
            return ResizeJournal(**d)
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, TypeError, KeyError):
            # Corrupt journal is itself reportable, never fatal (§20.11)
            return ResizeJournal(target="?", side="?", size_bytes=0,
                                 phase="corrupt")

    @staticmethod
    def clear(path: str = JOURNAL_PATH) -> None:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def recovery_action(journal: "ResizeJournal | None",
                    side_exists: bool, target_exists: bool) -> str:
    """Map crash state to the §26.2 recovery table. Returns an action id."""
    if journal is None:
        return "report_stray_side" if side_exists else "none"
    if journal.phase == "corrupt":
        return "report_corrupt_journal"
    if journal.phase == "building":
        return "delete_side_restart"          # old target intact
    if journal.phase == "switching":
        if side_exists:
            return "reactivate_old_delete_side"   # crashed before rename
        return "activate_new_continue"            # crashed after rename
    if journal.phase == "activated":
        return "resume_reconfigure"
    return "report_corrupt_journal"


# ---------------------------------------------------------------- backup manifest (§9)
@dataclass
class BackupEntry:
    path: str
    backup: str | None
    existed: bool


def make_manifest(entries: list[BackupEntry], created_at: str) -> dict:
    return {"created_at": created_at,
            "files": [asdict(e) for e in entries]}


def rollback_plan(manifest: dict) -> list[tuple[str, str, str | None]]:
    """Return [(action, path, backup)] — 'restore' or 'remove' per §9."""
    plan = []
    for f in manifest["files"]:
        if f["existed"]:
            plan.append(("restore", f["path"], f["backup"]))
        else:
            plan.append(("remove", f["path"], None))
    return plan
