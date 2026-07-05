"""v1.1 test block (spec SS12 tests 25-28, v1.8)."""
import json
import subprocess
import sys
from pathlib import Path

from ubuntu_hibernate_wizard.state import state_manager as sm
from ubuntu_hibernate_wizard import cli


# ---- test 25: notify on state change only, once per drift
def test_notify_only_on_drift_and_once():
    ok = {"schema_version": 1, "all_ok": True, "errors": []}
    drift = {"schema_version": 1, "all_ok": False, "errors": ["offset stale"]}
    assert not sm.should_notify(ok, None)              # healthy -> never
    assert not sm.should_notify(None, None)            # no status -> never
    assert sm.should_notify(drift, None)               # new drift -> notify
    h = sm.status_hash(drift)
    assert not sm.should_notify(drift, h)              # same drift -> once only
    drift2 = {"schema_version": 1, "all_ok": False, "errors": ["uuid wrong"]}
    assert sm.should_notify(drift2, h)                 # different drift -> notify


# ---- test 26: guard-status round-trip + corrupt handling
def test_guard_status_roundtrip_and_corrupt(tmp_path):
    p = str(tmp_path / "guard-status.json")
    sm.write_guard_status(False, ["offset stale"], "2026-07-05T12:00:00", p)
    st = sm.load_guard_status(p)
    assert st["all_ok"] is False and st["errors"] == ["offset stale"]
    (tmp_path / "guard-status.json").write_text("{nope")
    assert sm.load_guard_status(p) is None             # corrupt -> None
    (tmp_path / "guard-status.json").write_text(
        json.dumps({"schema_version": 99, "all_ok": True}))
    assert sm.load_guard_status(p) is None             # unknown version -> None


# ---- test 27: provenance - pre-existing swap never offered for deletion
def test_preexisting_swap_never_deletable(tmp_path):
    p = str(tmp_path / "state.json")
    st = sm.save_state("/swap.img", "d76e67b3-404f-461e-a961-7963664d66b3",
                       5986304, "2026-07-05T12:00:00", True,
                       swap_preexisting=True, path=p)
    assert st["schema_version"] == 1
    assert not sm.may_offer_swap_deletion(sm.load_state(p))
    st2 = sm.save_state("/swap.img", "d76e67b3-404f-461e-a961-7963664d66b3",
                        5986304, "t", False, swap_preexisting=False, path=p)
    assert sm.may_offer_swap_deletion(st2)             # wizard-created -> ok
    assert not sm.may_offer_swap_deletion(None)        # unknown -> safe default
    assert not sm.may_offer_swap_deletion({})          # missing field -> safe


# ---- test 28: CLI exit codes and JSON schema
def test_cli_exit_codes_defined():
    assert (cli.EXIT_OK, cli.EXIT_MISMATCH, cli.EXIT_CANNOT_CHECK) == (0, 2, 3)


def test_cli_verify_emits_valid_json_and_documented_code():
    r = subprocess.run([sys.executable, "-m",
                        "ubuntu_hibernate_wizard.main", "--verify"],
                       capture_output=True, text=True,
                       cwd=Path(__file__).resolve().parents[1])
    assert r.returncode in (cli.EXIT_MISMATCH, cli.EXIT_CANNOT_CHECK)
    out = json.loads(r.stdout)                          # schema-valid JSON
    assert "errors" in out and out["schema_version"] == 1
