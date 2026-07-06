"""Conservative encrypted-swap evidence collection.

The public release policy is deliberately conservative: any active encrypted
swap or ambiguous device-mapper swap is blocked from automatic resume
configuration unless a future release implements and tests a safe path for that
exact encryption model.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


_RANDOM_KEY_TOKENS = {"/dev/urandom", "/dev/random", "none", "-"}


@dataclass(slots=True)
class CrypttabEntry:
    """One parsed /etc/crypttab entry."""

    name: str
    source: str
    keyfile: str = ""
    options: list[str] = field(default_factory=list)

    @property
    def mapper_path(self) -> str:
        return f"/dev/mapper/{self.name}"

    @property
    def uses_random_key(self) -> bool:
        lower_options = {o.lower() for o in self.options}
        key = (self.keyfile or "").strip().lower()
        return key in _RANDOM_KEY_TOKENS or "swap" in lower_options or "random" in lower_options

    @property
    def has_swap_option(self) -> bool:
        return any(o.lower() == "swap" or o.lower().startswith("swap,") for o in self.options)


def parse_crypttab(text: str) -> tuple[list[CrypttabEntry], list[str]]:
    """Parse /etc/crypttab without raising on malformed public-user systems."""
    entries: list[CrypttabEntry] = []
    warnings: list[str] = []
    for line_no, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            warnings.append(f"Malformed crypttab line {line_no}: too few fields")
            continue
        name = parts[0]
        source = parts[1]
        keyfile = parts[2] if len(parts) >= 3 else ""
        options: list[str] = []
        if len(parts) >= 4:
            options = [opt.strip() for opt in parts[3].split(",") if opt.strip()]
        entries.append(CrypttabEntry(name=name, source=source, keyfile=keyfile, options=options))
    return entries, warnings


def _walk_lsblk_nodes(raw: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], parent: dict[str, Any] | None = None) -> None:
        clone = dict(node)
        if parent:
            clone["_parent_name"] = parent.get("name")
            clone["_parent_kname"] = parent.get("kname")
            clone["_parent_type"] = parent.get("type")
            clone["_parent_fstype"] = parent.get("fstype")
            clone["_parent_uuid"] = parent.get("uuid")
        nodes.append(clone)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, node)

    try:
        for node in raw.get("blockdevices", []) if isinstance(raw, dict) else []:
            if isinstance(node, dict):
                walk(node)
    except AttributeError:
        pass
    return nodes


def parse_lsblk_json(text: str) -> list[dict[str, Any]]:
    if not (text or "").strip():
        return []
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return []
    return _walk_lsblk_nodes(raw)


def _path_variants(path: str) -> set[str]:
    variants = {path}
    base = path.rsplit("/", 1)[-1]
    if base:
        variants.add(base)
        variants.add(f"/dev/{base}")
        variants.add(f"/dev/mapper/{base}")
    return variants


def _matches_token(token: str, path: str, *, uuid: str | None = None, partuuid: str | None = None) -> bool:
    token = (token or "").strip()
    if not token:
        return False
    variants = _path_variants(path)
    if token in variants:
        return True
    if token.startswith("UUID=") and uuid and token.split("=", 1)[1].lower() == uuid.lower():
        return True
    if token.startswith("PARTUUID=") and partuuid and token.split("=", 1)[1].lower() == partuuid.lower():
        return True
    return False


def _dmsetup_crypt_names(dmsetup_info: str) -> set[str]:
    """Extract likely crypt mapper names from dmsetup output.

    Accepts either `dmsetup info --columns` lines or more verbose fixture text.
    """
    names: set[str] = set()
    for raw in (dmsetup_info or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if "crypt" not in lower and "cr_" not in lower:
            continue
        # First whitespace-separated column is the name in the recommended
        # `dmsetup info --columns --noheadings -o name,uuid,blkdevname` output.
        name = line.split()[0]
        name = name.strip()
        if name and name not in {"Name:"}:
            names.add(name)
    return names


def classify_encryption_for_swap(
    path: str,
    *,
    crypttab_text: str = "",
    lsblk_json_text: str = "",
    dmsetup_info: str = "",
    uuid: str | None = None,
    partuuid: str | None = None,
    backing_device: str | None = None,
    root_source: str | None = None,
) -> dict[str, Any]:
    """Return conservative encryption metadata for one swap target."""
    evidence: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []
    crypttab_name: str | None = None
    crypttab_options: list[str] = []
    mapper_name: str | None = None
    mapper_is_crypt: bool | None = None
    parent_device: str | None = None
    classification = "plain_swapfile" if path.startswith("/") and not path.startswith("/dev/") else "plain_swap_partition"
    encrypted = False
    encryption_stable: bool | None = None

    entries, crypttab_warnings = parse_crypttab(crypttab_text)
    warnings.extend(crypttab_warnings)

    for entry in entries:
        if (
            _matches_token(entry.mapper_path, path, uuid=uuid, partuuid=partuuid)
            or _matches_token(entry.name, path, uuid=uuid, partuuid=partuuid)
            or _matches_token(entry.source, path, uuid=uuid, partuuid=partuuid)
            or (backing_device and _matches_token(entry.source, backing_device, uuid=uuid, partuuid=partuuid))
        ):
            encrypted = True
            crypttab_name = entry.name
            crypttab_options = list(entry.options)
            evidence.append("crypttab")
            if entry.uses_random_key:
                classification = "encrypted_random_key_swap"
                encryption_stable = False
                blockers.append("Encrypted swap uses a random/swap crypttab configuration and cannot be used as an automatic resume target")
            elif entry.has_swap_option:
                classification = "encrypted_swap_crypttab"
                encryption_stable = False
                blockers.append("Encrypted swap crypttab entry has swap option; automatic resume configuration is blocked")
            else:
                classification = "encrypted_persistent_swap"
                encryption_stable = False
                warnings.append("Persistent encrypted swap requires an explicitly implemented initramfs resume path before automatic configuration")
                blockers.append("Persistent encrypted swap is not automatically configured in this release")
            break

    nodes = parse_lsblk_json(lsblk_json_text)
    variants = _path_variants(path)
    for node in nodes:
        name = str(node.get("name") or "")
        kname = str(node.get("kname") or "")
        node_paths = {name, kname, f"/dev/{name}", f"/dev/{kname}"}
        if name:
            node_paths.add(f"/dev/mapper/{name}")
        if not (variants & node_paths):
            continue
        parent_device = parent_device or node.get("_parent_name") or node.get("pkname")
        ntype = str(node.get("type") or "").lower()
        fstype = str(node.get("fstype") or "").lower()
        ptype = str(node.get("_parent_type") or "").lower()
        pfstype = str(node.get("_parent_fstype") or "").lower()
        if ntype == "crypt" or fstype == "crypto_luks" or ptype == "crypt" or pfstype == "crypto_luks":
            encrypted = True
            evidence.append("lsblk")
            if classification.startswith("plain_"):
                classification = "encrypted_persistent_swap"
                encryption_stable = False
                blockers.append("lsblk indicates encrypted swap mapping; automatic resume path is not supported in this release")
        if ntype == "dm" or name.startswith("crypt"):
            mapper_name = mapper_name or name

    if path.startswith("/dev/mapper/"):
        mapper_name = mapper_name or path.rsplit("/", 1)[-1]
        crypt_names = _dmsetup_crypt_names(dmsetup_info)
        if mapper_name in crypt_names or any(path.endswith("/" + n) for n in crypt_names):
            encrypted = True
            mapper_is_crypt = True
            evidence.append("dmsetup")
            if classification.startswith("plain_"):
                classification = "encrypted_persistent_swap"
                encryption_stable = False
                blockers.append("dmsetup indicates encrypted mapper swap; automatic resume path is not supported in this release")
        elif not crypt_names and not evidence:
            mapper_is_crypt = None
            classification = "unknown_mapper_swap"
            blockers.append("Active /dev/mapper swap backing cannot be proven safe; automatic configuration is blocked")
        elif mapper_is_crypt is None:
            mapper_is_crypt = False

    # Swapfile on encrypted root is a different case from encrypted swap block
    # device. It is allowed to proceed through normal swapfile validation, but a
    # warning is useful for diagnostics/public support.
    if not encrypted and not path.startswith("/dev/") and root_source and str(root_source).startswith("/dev/mapper/"):
        classification = "swapfile_on_encrypted_root"
        warnings.append("Swap file appears to be on an encrypted root filesystem; validating as a swap file, not as encrypted swap block device")
        evidence.append("root_mapper")

    if crypttab_warnings and not encrypted and (path.startswith("/dev/mapper/") or "mapper" in (backing_device or "")):
        classification = "unknown_mapper_swap"
        blockers.append("crypttab could not be parsed completely and mapper swap status is ambiguous")

    return {
        "classification": classification,
        "encrypted": encrypted,
        "encryption_stable": encryption_stable,
        "encryption_source": sorted(set(evidence)),
        "crypttab_name": crypttab_name,
        "crypttab_options": crypttab_options,
        "mapper_name": mapper_name,
        "mapper_is_crypt": mapper_is_crypt,
        "parent_device": parent_device,
        "warnings": _dedupe(warnings),
        "blockers": _dedupe(blockers),
    }


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out
