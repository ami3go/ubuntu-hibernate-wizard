"""State file (Step 7) + guard status (SS27.1). Robust per SS20.11:
corrupt/unknown files never crash - reset to fresh detection."""
from __future__ import annotations

import hashlib
import json
import os

SCHEMA_VERSION = 1
STATE_DIR = os.path.expanduser("~/.config/ubuntu-hibernate-wizard")
STATE_PATH = os.path.join(STATE_DIR, "state.json")
GUARD_STATUS_PATH = "/var/lib/ubuntu-hibernate-wizard/guard-status.json"


def _atomic_json_write(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_state(path: str = STATE_PATH) -> dict | None:
    """Return state dict, or None if absent/corrupt/unknown-version (SS20.11)."""
    try:
        with open(path) as f:
            d = json.load(f)
        if d.get("schema_version") != SCHEMA_VERSION:
            return None            # unknown version -> fresh detection
        return d
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save_state(swap_file: str, fs_uuid: str, resume_offset: int,
               configured_at: str, reboot_required: bool,
               swap_preexisting: bool, path: str = STATE_PATH) -> dict:
    d = {
        "schema_version": SCHEMA_VERSION,
        "swap_file": swap_file,
        "swap_preexisting": swap_preexisting,   # provenance (SS27.4.3)
        "filesystem_uuid": fs_uuid,
        "resume_offset": str(resume_offset),
        "configured_at": configured_at,
        "reboot_required": reboot_required,
    }
    _atomic_json_write(path, d)
    return d


def may_offer_swap_deletion(state: dict | None) -> bool:
    """SS27.4.3: never offer to delete swap that pre-existed the wizard.
    Unknown provenance is treated as pre-existing (safe default)."""
    if not state:
        return False
    return state.get("swap_preexisting") is False


# ------------------------------------------------------------- guard (SS27.1)
def write_guard_status(all_ok: bool, errors: list[str], checked_at: str,
                       path: str = GUARD_STATUS_PATH) -> None:
    _atomic_json_write(path, {"schema_version": SCHEMA_VERSION,
                              "all_ok": all_ok, "errors": errors,
                              "checked_at": checked_at})
    os.chmod(path, 0o644)          # world-readable for session watcher


def load_guard_status(path: str = GUARD_STATUS_PATH) -> dict | None:
    return load_state(path)


def status_hash(status: dict) -> str:
    core = json.dumps({"all_ok": status.get("all_ok"),
                       "errors": status.get("errors")}, sort_keys=True)
    return hashlib.sha256(core.encode()).hexdigest()


def should_notify(status: dict | None, last_notified_hash: str | None) -> bool:
    """SS27.1: notify only on drift, and only once per distinct drift state."""
    if status is None or status.get("all_ok", True):
        return False
    return status_hash(status) != last_notified_hash
