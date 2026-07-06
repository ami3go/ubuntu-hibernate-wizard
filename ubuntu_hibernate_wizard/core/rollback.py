"""Hardened manifest-backed rollback support for Ubuntu Hibernate Wizard.

The privileged helper owns snapshot creation.  The pure planner in this module is
written so tests can exercise rollback decisions without touching the real host.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ubuntu_hibernate_wizard.constants import APP_VERSION

BACKUP_ROOT = "/var/backups/ubuntu-hibernate-wizard"
MANIFEST_VERSION = 2
BACKUP_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-f0-9]{6}$")
PLACEHOLDER_RE = re.compile(r"<[^>]+>|\*|__.*__")

# Managed-file allowlist for rollback-backed writes.  /etc/fstab is allowed
# only for the controlled managed-swapfile create/resize flow.
ALLOWLIST_FILES = {
    "/etc/initramfs-tools/conf.d/resume",
    "/etc/default/grub.d/hibernate-wizard.cfg",
    "/etc/fstab",
}

ALLOWLIST_DIRS = {
    "/etc/initramfs-tools/conf.d",
    "/etc/default/grub.d",
}

ROLLBACK_ELIGIBLE_STATUSES = {
    "failed",
    "completed",
    "in-progress",
    "rolled-back-partial",
    "rollback-failed",
}
STORED_STATUSES = {
    "in-progress",
    "completed",
    "failed",
    "rollback-in-progress",
    "rollback-failed",
    "rolled-back",
    "rolled-back-partial",
}


@dataclass
class ManifestFile:
    path: str
    backup: str | None
    existed: bool
    sha256_before: str | None
    sha256_after: str | None
    mode_before: int | None
    uid_before: int | None
    gid_before: int | None
    managed_by_wizard: bool = False
    write_order: int = 0


@dataclass
class ManifestDir:
    path: str
    existed: bool
    managed_by_wizard: bool = False


@dataclass
class RollbackManifest:
    schema_version: int
    backup_id: str
    created_at: str
    operation: str
    app_version: str
    status: str
    files: list[ManifestFile] = field(default_factory=list)
    dirs: list[ManifestDir] = field(default_factory=list)
    swap: dict[str, Any] | None = None
    rollback_results: list[dict[str, Any]] = field(default_factory=list)
    completed_at: str | None = None
    failed_step: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class RollbackAction:
    type: str
    path: str | None = None
    status: str = "pending"
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


class RollbackSecurityError(ValueError):
    """Raised when manifest/snapshot validation proves a snapshot unsafe."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_backup_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)


def validate_backup_id(backup_id: str) -> str:
    if not isinstance(backup_id, str) or not BACKUP_ID_RE.match(backup_id):
        raise RollbackSecurityError("INVALID_BACKUP_ID")
    return backup_id


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return bool(PLACEHOLDER_RE.search(value))
    if isinstance(value, dict):
        return any(_contains_placeholder(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_placeholder(v) for v in value)
    return False


def reject_placeholder_values(plan: dict[str, Any]) -> None:
    if _contains_placeholder(plan):
        raise RollbackSecurityError("PLACEHOLDER_IN_PLAN")


def hash_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fsync_dir(path: str | Path) -> None:
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: str | Path, data: bytes, *, mode: int = 0o644,
                       uid: int | None = None, gid: int | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, mode)
        if uid is not None or gid is not None:
            os.chown(tmp_name, 0 if uid is None else uid, 0 if gid is None else gid)
        os.replace(tmp_name, path)
        fsync_dir(path.parent)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: str | Path, data: dict[str, Any], *, mode: int = 0o600) -> None:
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(path, payload, mode=mode, uid=0 if os.geteuid() == 0 else None, gid=0 if os.geteuid() == 0 else None)


def _manifest_file_from_dict(d: dict[str, Any]) -> ManifestFile:
    return ManifestFile(
        path=d["path"], backup=d.get("backup"), existed=bool(d.get("existed")),
        sha256_before=d.get("sha256_before"), sha256_after=d.get("sha256_after"),
        mode_before=d.get("mode_before"), uid_before=d.get("uid_before"),
        gid_before=d.get("gid_before"), managed_by_wizard=bool(d.get("managed_by_wizard", False)),
        write_order=int(d.get("write_order", 0)),
    )


def _manifest_dir_from_dict(d: dict[str, Any]) -> ManifestDir:
    return ManifestDir(path=d["path"], existed=bool(d.get("existed")), managed_by_wizard=bool(d.get("managed_by_wizard", False)))


def manifest_to_dict(m: RollbackManifest) -> dict[str, Any]:
    d = asdict(m)
    # Keep stable key order for human review.
    return d


def manifest_from_dict(d: dict[str, Any]) -> RollbackManifest:
    if d.get("schema_version") != MANIFEST_VERSION:
        raise RollbackSecurityError("UNSUPPORTED_MANIFEST_SCHEMA")
    backup_id = validate_backup_id(d.get("backup_id"))
    status = d.get("status")
    if status not in STORED_STATUSES:
        raise RollbackSecurityError("UNSUPPORTED_MANIFEST_STATUS")
    return RollbackManifest(
        schema_version=MANIFEST_VERSION,
        backup_id=backup_id,
        created_at=d.get("created_at") or "",
        completed_at=d.get("completed_at"),
        operation=d.get("operation") or "unknown",
        app_version=d.get("app_version") or "unknown",
        status=status,
        failed_step=d.get("failed_step"),
        error_code=d.get("error_code"),
        error_message=d.get("error_message"),
        files=[_manifest_file_from_dict(x) for x in d.get("files", [])],
        dirs=[_manifest_dir_from_dict(x) for x in d.get("dirs", [])],
        swap=d.get("swap"),
        rollback_results=d.get("rollback_results", []),
    )


def snapshot_dir(backup_id: str, backup_root: str = BACKUP_ROOT) -> Path:
    validate_backup_id(backup_id)
    return Path(backup_root) / backup_id



def _safe_relative_backup_path(target_path: str) -> str:
    p = Path(target_path)
    if not p.is_absolute():
        raise RollbackSecurityError("UNSAFE_MANIFEST_PATH")
    return str(Path("files") / str(p).lstrip("/"))


def validate_target_path(path: str) -> str:
    if path not in ALLOWLIST_FILES:
        raise RollbackSecurityError("UNSAFE_MANIFEST_PATH")
    return path


def validate_dir_path(path: str) -> str:
    if path not in ALLOWLIST_DIRS:
        raise RollbackSecurityError("UNSAFE_MANIFEST_PATH")
    return path


def validate_metadata(mode: int | None, uid: int | None, gid: int | None) -> tuple[int, int, int]:
    if not isinstance(mode, int) or mode < 0 or mode > 0o7777 or (mode & 0o6000):
        raise RollbackSecurityError("UNSAFE_MANIFEST_METADATA")
    if uid != 0 or gid != 0:
        raise RollbackSecurityError("UNSAFE_MANIFEST_METADATA")
    return mode, uid, gid


def _validate_snapshot_dir(path: Path, backup_root: str) -> None:
    root = Path(backup_root).resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RollbackSecurityError("SNAPSHOT_OUTSIDE_BACKUP_ROOT") from exc
    if path.is_symlink():
        raise RollbackSecurityError("SNAPSHOT_DIR_SYMLINK")
    st = path.stat()
    if (st.st_mode & 0o022) != 0:
        raise RollbackSecurityError("SNAPSHOT_DIR_GROUP_OR_WORLD_WRITABLE")
    if os.geteuid() == 0 and st.st_uid != 0:
        raise RollbackSecurityError("SNAPSHOT_DIR_NOT_ROOT_OWNED")


def _validate_backup_rel(snapshot: Path, rel: str | None) -> Path | None:
    if rel is None:
        return None
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise RollbackSecurityError("UNSAFE_BACKUP_PATH")
    full = (snapshot / rel_path).resolve()
    try:
        full.relative_to(snapshot.resolve())
    except ValueError as exc:
        raise RollbackSecurityError("BACKUP_PATH_OUTSIDE_SNAPSHOT") from exc
    if full.exists():
        if full.is_symlink() or not full.is_file():
            raise RollbackSecurityError("UNSAFE_BACKUP_FILE")
    return full


def validate_manifest_security(backup_id: str, backup_root: str = BACKUP_ROOT) -> RollbackManifest:
    backup_id = validate_backup_id(backup_id)
    snap = snapshot_dir(backup_id, backup_root)
    _validate_snapshot_dir(snap, backup_root)
    mp = snap / "manifest.json"
    if mp.is_symlink():
        raise RollbackSecurityError("MANIFEST_SYMLINK")
    with open(mp, "r", encoding="utf-8") as f:
        raw = json.load(f)
    m = manifest_from_dict(raw)
    if m.backup_id != backup_id:
        raise RollbackSecurityError("MANIFEST_ID_MISMATCH")
    for mf in m.files:
        validate_target_path(mf.path)
        _validate_backup_rel(snap, mf.backup)
        if mf.existed:
            validate_metadata(mf.mode_before, mf.uid_before, mf.gid_before)
    for md in m.dirs:
        validate_dir_path(md.path)
    validate_swap_manifest_names(m)
    return m


def validate_swap_path(path: str) -> str:
    if path not in ("/swap.img", "/swapfile"):
        raise RollbackSecurityError("UNSAFE_SWAP_PATH")
    return path


def expected_old_swap_backup_name(swap_path: str, backup_id: str) -> str:
    return f"{Path(validate_swap_path(swap_path)).name}.uhw-backup-{validate_backup_id(backup_id)}"


def expected_rollback_current_name(swap_path: str, backup_id: str) -> str:
    return f"{Path(validate_swap_path(swap_path)).name}.uhw-rollback-current-{validate_backup_id(backup_id)}"


def validate_swap_sibling(path: str, name: str | None, backup_id: str, *, kind: str) -> Path | None:
    if not name:
        return None
    path = validate_swap_path(path)
    if kind == "old":
        expected = expected_old_swap_backup_name(path, backup_id)
    elif kind == "current":
        expected = expected_rollback_current_name(path, backup_id)
    elif kind == "side":
        expected = f"{Path(path).name}.new"
    else:
        raise ValueError(kind)
    if name != expected:
        raise RollbackSecurityError("UNSAFE_SWAP_SIBLING_NAME")
    full = Path(path).with_name(name)
    if full.exists():
        st = full.lstat()
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise RollbackSecurityError("UNSAFE_SWAP_SIBLING_FILE")
        if st.st_uid != 0 and os.geteuid() == 0:
            raise RollbackSecurityError("UNSAFE_SWAP_SIBLING_OWNER")
        if (st.st_mode & 0o777) != 0o600:
            raise RollbackSecurityError("UNSAFE_SWAP_SIBLING_MODE")
    return full


def validate_swap_manifest_names(m: RollbackManifest) -> None:
    if not m.swap:
        return
    path = validate_swap_path(m.swap.get("path"))
    bid = m.backup_id
    validate_swap_sibling(path, m.swap.get("old_swap_backup_name"), bid, kind="old")
    validate_swap_sibling(path, m.swap.get("side_file_name"), bid, kind="side")
    validate_swap_sibling(path, m.swap.get("rollback_current_name"), bid, kind="current")


class BackupManager:
    """Create/update a helper-owned rollback snapshot manifest."""

    def __init__(self, backup_id: str, backup_root: str = BACKUP_ROOT) -> None:
        self.backup_id = validate_backup_id(backup_id)
        self.backup_root = backup_root
        self.snapshot = snapshot_dir(backup_id, backup_root)
        self._manifest = validate_manifest_security(backup_id, backup_root)

    @classmethod
    def begin(cls, operation: str, backup_root: str = BACKUP_ROOT, app_version: str = APP_VERSION) -> "BackupManager":
        if operation not in {"apply", "repair", "remove-hibernation", "rollback-safety-snapshot"}:
            raise RollbackSecurityError("UNSUPPORTED_OPERATION")
        backup_id = new_backup_id()
        root = Path(backup_root)
        root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(root, 0o700)
        except PermissionError:
            pass
        snap = snapshot_dir(backup_id, backup_root)
        snap.mkdir(mode=0o700)
        try:
            os.chmod(snap, 0o700)
            if os.geteuid() == 0:
                os.chown(snap, 0, 0)
        except PermissionError:
            pass
        m = RollbackManifest(
            schema_version=MANIFEST_VERSION,
            backup_id=backup_id,
            created_at=utc_now_iso(),
            operation=operation,
            app_version=app_version,
            status="in-progress",
            files=[],
            dirs=[],
            swap=None,
            rollback_results=[],
        )
        atomic_write_json(snap / "manifest.json", manifest_to_dict(m), mode=0o600)
        return cls(backup_id, backup_root)

    @property
    def manifest(self) -> RollbackManifest:
        return self._manifest

    def reload(self) -> RollbackManifest:
        self._manifest = validate_manifest_security(self.backup_id, self.backup_root)
        return self._manifest

    def save(self) -> None:
        atomic_write_json(self.snapshot / "manifest.json", manifest_to_dict(self._manifest), mode=0o600)

    def _find_file(self, path: str) -> ManifestFile | None:
        for f in self._manifest.files:
            if f.path == path:
                return f
        return None

    def _next_write_order(self) -> int:
        return max((f.write_order for f in self._manifest.files), default=0) + 1

    def record_created_dir(self, path: str) -> None:
        path = validate_dir_path(path)
        if any(d.path == path for d in self._manifest.dirs):
            return
        self._manifest.dirs.append(ManifestDir(path=path, existed=Path(path).exists(), managed_by_wizard=True))
        self.save()

    def maybe_record_parent_dir(self, path: str) -> None:
        parent = str(Path(path).parent)
        if parent in ALLOWLIST_DIRS and not Path(parent).exists():
            self.record_created_dir(parent)

    def record_before_write(self, path: str, managed_by_wizard: bool = False) -> None:
        path = validate_target_path(path)
        if self._find_file(path):
            return
        p = Path(path)
        self.maybe_record_parent_dir(path)
        existed = p.exists()
        backup_rel = None
        sha_before = None
        mode = uid = gid = None
        if existed:
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                raise RollbackSecurityError("UNSAFE_TARGET_FILE")
            backup_rel = _safe_relative_backup_path(path)
            dest = self.snapshot / backup_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".tmp")
            shutil.copy2(p, tmp, follow_symlinks=False)
            with open(tmp, "rb") as f:
                os.fsync(f.fileno())
            os.replace(tmp, dest)
            fsync_dir(dest.parent)
            sha_before = hash_file(p)
            mode = stat.S_IMODE(st.st_mode)
            uid = st.st_uid
            gid = st.st_gid
        self._manifest.files.append(ManifestFile(
            path=path,
            backup=backup_rel,
            existed=existed,
            sha256_before=sha_before,
            sha256_after=None,
            mode_before=mode,
            uid_before=uid,
            gid_before=gid,
            managed_by_wizard=managed_by_wizard,
            write_order=self._next_write_order(),
        ))
        self.save()

    def record_after_write(self, path: str) -> None:
        path = validate_target_path(path)
        mf = self._find_file(path)
        if mf is None:
            raise RollbackSecurityError("WRITE_NOT_RECORDED")
        if Path(path).exists():
            mf.sha256_after = hash_file(path)
        self.save()

    def set_swap_side_file(self, name: str | None) -> None:
        if self._manifest.swap is not None:
            self._manifest.swap["side_file_name"] = name
            self.save()

    def set_rollback_current_name(self, name: str) -> None:
        if self._manifest.swap is not None:
            self._manifest.swap["rollback_current_name"] = name
            self.save()

    def mark_status(self, status: str, **metadata: Any) -> None:
        if status not in STORED_STATUSES:
            raise RollbackSecurityError("BAD_STATUS")
        self._manifest.status = status
        if status in {"completed", "failed", "rolled-back", "rolled-back-partial", "rollback-failed"}:
            self._manifest.completed_at = utc_now_iso()
        for key, value in metadata.items():
            if key == "failed_step":
                self._manifest.failed_step = value
            elif key == "error_code":
                self._manifest.error_code = value
            elif key in {"message", "error_message"}:
                self._manifest.error_message = value
            elif key == "rollback_results":
                self._manifest.rollback_results = value
            else:
                # Preserve extra report fields without extending the dataclass surface.
                self._manifest.rollback_results.append({key: value})
        self.save()


class LocalFileSystemProbe:
    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def is_file(self, path: str) -> bool:
        return Path(path).is_file()

    def is_dir(self, path: str) -> bool:
        return Path(path).is_dir()

    def is_empty_dir(self, path: str) -> bool:
        p = Path(path)
        return p.is_dir() and not any(p.iterdir())

    def sha256(self, path: str) -> str | None:
        try:
            return hash_file(path)
        except FileNotFoundError:
            return None


class RollbackPlanner:
    def __init__(self, backup_root: str = BACKUP_ROOT) -> None:
        self.backup_root = backup_root

    def build_plan(self, manifest: RollbackManifest, current_fs: LocalFileSystemProbe | None = None) -> list[RollbackAction]:
        current_fs = current_fs or LocalFileSystemProbe()
        actions: list[RollbackAction] = []
        if manifest.swap:
            actions.extend(self._swap_actions(manifest, current_fs))
        for mf in sorted(manifest.files, key=lambda f: f.write_order, reverse=True):
            actions.append(self._file_action(manifest, mf, current_fs))
        for md in sorted(manifest.dirs, key=lambda d: d.path.count("/"), reverse=True):
            if not md.existed and md.managed_by_wizard:
                if current_fs.is_empty_dir(md.path):
                    actions.append(RollbackAction("remove-created-empty-dir", md.path, "will-run", "wizard-created directory is empty"))
                elif current_fs.exists(md.path):
                    actions.append(RollbackAction("remove-created-empty-dir", md.path, "skip", "DIRECTORY_NOT_EMPTY"))
        actions.extend(self._post_actions(actions))
        return actions

    def _backup_file_exists(self, manifest: RollbackManifest, backup: str | None) -> bool:
        if backup is None:
            return False
        p = _validate_backup_rel(snapshot_dir(manifest.backup_id, self.backup_root), backup)
        return bool(p and p.exists())

    def _file_action(self, manifest: RollbackManifest, mf: ManifestFile, fs: LocalFileSystemProbe) -> RollbackAction:
        validate_target_path(mf.path)
        if mf.existed:
            if not self._backup_file_exists(manifest, mf.backup):
                return RollbackAction("restore-file", mf.path, "skip", "BACKUP_FILE_MISSING", {"backup": mf.backup})
            current = fs.sha256(mf.path) if fs.exists(mf.path) else None
            if mf.sha256_after is None:
                if current == mf.sha256_before:
                    return RollbackAction("restore-file", mf.path, "skip", "NO_RESTORE_NEEDED_ORIGINAL_CONTENT")
                return RollbackAction("restore-file", mf.path, "skip", "SKIPPED_UNCERTAIN_AFTER_HASH")
            if current == mf.sha256_after:
                return RollbackAction("restore-file", mf.path, "will-run", "current hash matches wizard-written hash", {"backup": mf.backup})
            return RollbackAction("restore-file", mf.path, "skip", "SKIPPED_USER_MODIFIED_EXISTING_FILE")
        # Wizard-created file.
        if not fs.exists(mf.path):
            return RollbackAction("remove-created-file", mf.path, "skip", "ALREADY_ABSENT")
        if mf.sha256_after is None:
            return RollbackAction("remove-created-file", mf.path, "skip", "SKIPPED_UNCERTAIN_AFTER_HASH")
        current = fs.sha256(mf.path)
        if current == mf.sha256_after:
            return RollbackAction("remove-created-file", mf.path, "will-run", "current hash matches wizard-created file")
        return RollbackAction("remove-created-file", mf.path, "skip", "SKIPPED_USER_MODIFIED_CREATED_FILE")

    def _swap_actions(self, manifest: RollbackManifest, fs: LocalFileSystemProbe) -> list[RollbackAction]:
        s = manifest.swap or {}
        path = validate_swap_path(s.get("path"))
        mode = s.get("rollback_mode")
        if mode == "restore-retained-old-file" or (s.get("existed_before") and s.get("old_swap_backup_name")):
            old = validate_swap_sibling(path, s.get("old_swap_backup_name"), manifest.backup_id, kind="old")
            if not old or not old.exists():
                return [RollbackAction("restore-old-swap-file", path, "skip", "OLD_SWAP_BACKUP_MISSING")]
            return [RollbackAction("restore-old-swap-file", path, "will-run", "retained old swap file exists", {"old_swap_backup_name": old.name})]
        if mode == "remove-wizard-created-swap" or (s.get("existed_before") is False):
            if fs.exists(path):
                return [RollbackAction("remove-wizard-created-swap", path, "will-run", "manifest proves swap did not exist before wizard")]
            return [RollbackAction("remove-wizard-created-swap", path, "skip", "ALREADY_ABSENT")]
        if s.get("side_file_name"):
            return [RollbackAction("cleanup-side-swap-file", path, "will-run", "aborted side file is recorded", {"side_file_name": s.get("side_file_name")})]
        return []

    def _post_actions(self, actions: list[RollbackAction]) -> list[RollbackAction]:
        changed = {a.path for a in actions if a.status == "will-run" and a.path}
        post: list[RollbackAction] = []
        if "/etc/default/grub" in changed or "/etc/fstab" in changed:
            post.append(RollbackAction("rerun-update-grub", None, "will-run", "GRUB/fstab changed"))
        if "/etc/initramfs-tools/conf.d/resume" in changed:
            post.append(RollbackAction("rerun-update-initramfs", None, "will-run", "initramfs resume config changed"))
        if any(p and p.startswith("/etc/systemd/") for p in changed):
            post.append(RollbackAction("reload-systemd-daemon", None, "will-run", "systemd drop-ins changed"))
        return post


def list_snapshots(backup_root: str = BACKUP_ROOT, active_backup_id: str | None = None) -> list[dict[str, Any]]:
    root = Path(backup_root)
    items: list[dict[str, Any]] = []
    if not root.exists():
        return items
    for child in sorted(root.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        mp = child / "manifest.json"
        if not mp.exists():
            items.append({
                "backup_id": None,
                "dir_name": child.name,
                "backup_dir": str(child),
                "display_status": "legacy backup - manual restore only",
                "can_preview": False,
                "can_rollback": False,
                "manual_only": True,
            })
            continue
        try:
            m = validate_manifest_security(child.name, backup_root)
            display_status = m.status
            if m.status in {"in-progress", "rollback-in-progress"} and m.backup_id != active_backup_id:
                display_status = "interrupted"
            can = m.status in ROLLBACK_ELIGIBLE_STATUSES
            if display_status == "interrupted":
                can = True
            items.append({
                "backup_id": m.backup_id,
                "backup_dir": str(child),
                "created_at": m.created_at,
                "operation": m.operation,
                "status": m.status,
                "display_status": display_status,
                "file_count": len(m.files),
                "swap": bool(m.swap),
                "can_preview": can,
                "can_rollback": can,
                "manual_only": False,
            })
        except Exception as exc:  # noqa: BLE001 - recovery list must not crash
            items.append({
                "backup_id": child.name if BACKUP_ID_RE.match(child.name) else None,
                "dir_name": None if BACKUP_ID_RE.match(child.name) else child.name,
                "backup_dir": str(child),
                "display_status": "unsafe" if isinstance(exc, RollbackSecurityError) else "corrupt",
                "error": str(exc),
                "can_preview": False,
                "can_rollback": False,
                "manual_only": False,
            })
    return items
