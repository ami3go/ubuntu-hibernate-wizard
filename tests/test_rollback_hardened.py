import json
import re
from pathlib import Path

import pytest

from ubuntu_hibernate_wizard.backend.privileged_helper import Helper
from ubuntu_hibernate_wizard.core import rollback as rb


def test_backup_id_format_uses_hardened_pattern():
    bid = rb.new_backup_id()
    assert re.match(r"^[0-9]{8}-[0-9]{6}-[a-f0-9]{6}$", bid)


def test_placeholder_plan_rejected():
    h = Helper()
    with pytest.raises(rb.RollbackSecurityError):
        h.cmd_submit_plan({"plan": {"schema_version": 1, "operation": "apply", "commands": {
            "resize-swap": {"swap_file": "/swap.img", "backup_id": "<filled-after-begin-operation>"}
        }}})


def test_legacy_update_commands_are_not_public_persistent_mutations():
    import ubuntu_hibernate_wizard.backend.privileged_helper as ph
    assert "update-grub-resume" in ph.DISABLED_LEGACY_MUTATING
    assert "update-initramfs-resume" in ph.DISABLED_LEGACY_MUTATING
    assert "update-grub-resume" not in ph.MUTATING
    assert "update-initramfs-resume" not in ph.MUTATING
    h = Helper()
    with pytest.raises(ValueError):
        h.cmd_submit_plan({"plan": {"schema_version": 1, "operation": "apply", "commands": {
            "update-grub-resume": {"uuid": "d76e67b3-404f-461e-a961-7963664d66b3", "offset": 1024}
        }}})


def test_rollback_is_the_only_persistent_mutating_command():
    import ubuntu_hibernate_wizard.backend.privileged_helper as ph
    assert ph.MUTATING == {"rollback"}
    assert "cleanup-old-swap-backup" not in ph.MUTATING


def test_resize_swap_command_rejected_in_v042():
    h = Helper()
    with pytest.raises(ValueError):
        h.cmd_submit_plan({"plan": {"schema_version": 1, "operation": "apply", "commands": {
            "resize-swap": {"swap_file": "/swap.img", "size_mb": 1024}
        }}})


def test_created_file_with_uncertain_after_hash_is_skipped():
    m = rb.RollbackManifest(
        schema_version=2,
        backup_id="20260705-180000-a1b2c3",
        created_at="2026-07-05T18:00:00Z",
        operation="apply",
        app_version="0.36.0",
        status="failed",
        files=[rb.ManifestFile("/etc/initramfs-tools/conf.d/resume", None, False, None, None, None, None, None, True, 1)],
        dirs=[],
        swap=None,
        rollback_results=[],
    )
    class FS:
        def exists(self, path): return True
        def sha256(self, path): return "abc"
        def is_empty_dir(self, path): return False
    actions = rb.RollbackPlanner().build_plan(m, FS())
    assert actions[0].type == "remove-created-file"
    assert actions[0].status == "skip"
    assert actions[0].reason == "SKIPPED_UNCERTAIN_AFTER_HASH"


def test_legacy_listing_uses_dir_name_not_backup_id(tmp_path):
    root = tmp_path / "backups"
    legacy = root / "20260705-175900"
    legacy.mkdir(parents=True)
    items = rb.list_snapshots(str(root))
    assert items[0]["backup_id"] is None
    assert items[0]["dir_name"] == "20260705-175900"
    assert items[0]["manual_only"] is True


def test_reboot_command_is_not_exposed_after_manual_reboot_change():
    import ubuntu_hibernate_wizard.backend.privileged_helper as ph
    assert "reboot-system" not in ph.MUTATING
    assert not hasattr(Helper(), "cmd_reboot_system")
