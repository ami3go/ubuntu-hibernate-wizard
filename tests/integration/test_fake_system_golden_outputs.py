from __future__ import annotations

import json
from pathlib import Path

import pytest
import zipfile

from ubuntu_hibernate_wizard.services.hibernate_planner import build_modification_plan
from ubuntu_hibernate_wizard.services.log_exporter import write_diagnostic_zip
from ubuntu_hibernate_wizard.services.system_probe import load_fake_system_data, profile_from_probe_data

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "fake_systems"
REQUIRED_FIXTURES = {
    "swapfile_ok",
    "swapfile_too_small",
    "swap_partition_ok",
    "swap_partition_too_small",
    "swapfile_and_partition",
    "no_swap",
    "encrypted_swap_crypttab_random_key",
    "encrypted_swap_crypttab_named_mapper",
    "encrypted_swap_mapper_active",
    "encrypted_swap_unknown_mapper",
    "encrypted_root_plain_swapfile",
    "zram_only",
    "btrfs_swapfile",
    "missing_resume_config",
    "malformed_fstab",
    "malformed_crypttab",
    "read_only_filesystem",
    "dmsetup_unavailable",
}


def _fixture_names() -> list[str]:
    return sorted(p.name for p in FIXTURE_ROOT.iterdir() if p.is_dir())


def _load_expected(path: Path, name: str):
    return json.loads((path / "expected" / name).read_text(encoding="utf-8"))


def _plan_expected(profile):
    if not profile.recommended_target:
        return {"available": False, "can_apply": False, "blocking_reasons": profile.blocking_reasons}
    plan = build_modification_plan(profile, profile.recommended_target)
    return {
        "available": True,
        "can_apply": plan.can_apply,
        "selected_target": plan.selected_target.path,
        "steps": [s.id for s in plan.steps],
        "planned_files": plan.planned_files,
        "warnings": plan.warnings,
        "blocking_reasons": plan.blocking_reasons,
    }


def test_all_required_fake_system_fixtures_exist():
    assert REQUIRED_FIXTURES <= set(_fixture_names())


@pytest.mark.parametrize("name", _fixture_names())
def test_fake_system_fixture_matches_golden_outputs(name):
    fixture = FIXTURE_ROOT / name
    data = load_fake_system_data(fixture)
    profile = profile_from_probe_data(data)
    warnings = []
    for c in profile.candidates:
        warnings.extend(c.warnings)

    assert [c.to_dict() for c in profile.candidates] == _load_expected(fixture, "swap-targets.json")
    assert profile.blocking_reasons == _load_expected(fixture, "blockers.json")
    assert warnings == _load_expected(fixture, "warnings.json")
    assert _plan_expected(profile) == _load_expected(fixture, "plan.json")


@pytest.mark.parametrize("name", _fixture_names())
def test_fake_system_fixture_has_documented_expected_outputs(name):
    fixture = FIXTURE_ROOT / name
    for rel in [
        "files/proc-swaps.txt",
        "files/proc-meminfo.txt",
        "files/etc-fstab.txt",
        "files/etc-crypttab.txt",
        "files/etc-default-grub.txt",
        "files/sys-power-state.txt",
        "files/sys-power-resume.txt",
        "commands/lsblk.json",
        "commands/swapon-show.txt",
        "commands/findmnt-root.txt",
        "commands/dmsetup-info.txt",
        "expected/swap-targets.json",
        "expected/blockers.json",
        "expected/warnings.json",
        "expected/plan.json",
        "expected/diagnostic-summary.txt",
        "README.md",
    ]:
        assert (fixture / rel).exists(), f"{name} missing {rel}"


@pytest.mark.parametrize("name", _fixture_names())
def test_fake_system_diagnostic_zip_fixture_summary_matches_golden(name, tmp_path):
    fixture = FIXTURE_ROOT / name
    data = load_fake_system_data(fixture)
    profile = profile_from_probe_data(data)
    plan = build_modification_plan(profile, profile.recommended_target) if profile.recommended_target else None
    zip_path = write_diagnostic_zip(tmp_path / f"{name}.zip", profile, plan)
    with zipfile.ZipFile(zip_path) as zf:
        generated = zf.read("fixture-summary.txt").decode("utf-8")
    expected = (fixture / "expected" / "diagnostic-summary.txt").read_text(encoding="utf-8")
    assert generated == expected
