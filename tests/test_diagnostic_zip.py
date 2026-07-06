from __future__ import annotations

import json
import zipfile
from pathlib import Path

from ubuntu_hibernate_wizard.backend.session import HelperSession
from ubuntu_hibernate_wizard.services.log_exporter import redact_diagnostic_text
from ubuntu_hibernate_wizard.services.system_probe import load_fake_system

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fake_systems" / "swapfile_ok"


def test_diagnostic_export_is_zip_and_has_required_files(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    session = HelperSession(fake_system=str(FIXTURE))
    session.detect()
    path = Path(session.export_diagnostics())
    assert path.suffix == ".zip"
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "summary.txt" in names
        assert "swap-detection.json" in names
        assert "commands/swapon-show.txt" in names
        assert "configs/fstab.redacted.txt" in names
        manifest = json.loads(zf.read("manifest.json").decode())
        assert manifest["redaction"]["enabled"] is True


def test_diagnostic_redaction_removes_sensitive_patterns():
    text = """
Host: lab-pc
/home/alex/project/file
/etc/machine-id: 0123456789abcdef
-----BEGIN OPENSSH PRIVATE KEY-----abc-----END OPENSSH PRIVATE KEY-----
api_token=abcdef
Disk Serial: S12345
"""
    redacted = redact_diagnostic_text(text)
    assert "lab-pc" not in redacted
    assert "/home/alex" not in redacted
    assert "0123456789abcdef" not in redacted
    assert "OPENSSH PRIVATE KEY" not in redacted
    assert "abcdef" not in redacted
    assert "S12345" not in redacted


def test_public_diagnostic_zip_redacts_uuids_by_default(tmp_path):
    profile = load_fake_system(FIXTURE)
    out = tmp_path / "diag.zip"
    from ubuntu_hibernate_wizard.services.log_exporter import write_diagnostic_zip
    write_diagnostic_zip(out, profile)
    with zipfile.ZipFile(out) as zf:
        payload = zf.read("swap-detection.json").decode("utf-8")
        summary = zf.read("summary.txt").decode("utf-8")
    assert "d76e67b3-404f-461e-a961-7963664d66b3" not in payload
    assert "d76e67b3-404f-461e-a961-7963664d66b3" not in summary
    assert "<redacted-uuid>" in payload


def test_uuid_redaction_is_explicitly_optional():
    text = "UUID=d76e67b3-404f-461e-a961-7963664d66b3"
    assert "d76e67b3-404f-461e-a961-7963664d66b3" in redact_diagnostic_text(text)
    assert "<redacted-uuid>" in redact_diagnostic_text(text, redact_uuids=True)
