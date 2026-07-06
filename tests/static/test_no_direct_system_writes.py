from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "ubuntu_hibernate_wizard"
APPROVED_MUTATION_MODULES = {
    "ubuntu_hibernate_wizard/backend/privileged_helper.py",
    "ubuntu_hibernate_wizard/core/rollback.py",
}
DANGEROUS_PATTERNS = [
    re.compile(r"open\(['\"]/(etc/fstab|etc/default/grub)"),
    re.compile(r"Path\(['\"]/(etc/fstab|etc/default/grub)"),
    re.compile(r"subprocess\.(run|Popen|check_call|check_output).*\b(swapon|swapoff|update-grub|update-initramfs|mkswap|fallocate|dd)\b"),
]


def _py_files():
    for path in APP.rglob("*.py"):
        yield path


def test_no_direct_protected_config_writes_or_dangerous_command_bypass():
    violations = []
    for path in _py_files():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel in APPROVED_MUTATION_MODULES:
            continue
        for pattern in DANGEROUS_PATTERNS:
            if pattern.search(text):
                violations.append(rel)
                break
    assert violations == []


def test_gui_does_not_import_privileged_helper_directly():
    gui_source = (APP / "ui" / "wizard_window.py").read_text(encoding="utf-8")
    assert "privileged_helper" not in gui_source
    assert "pkexec" not in gui_source


def test_public_session_uses_one_shot_apply_not_legacy_mutating_commands():
    session_source = (APP / "backend" / "session.py").read_text(encoding="utf-8")
    assert '"--action", "apply-plan"' in session_source
    for legacy in ["begin-operation", "finish-operation", "mark-operation-failed", "update-grub-resume", "update-initramfs-resume", "cleanup-old-swap-backup"]:
        assert legacy not in session_source
