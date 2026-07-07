from pathlib import Path


def test_technical_details_explain_change_impacts() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    technical = source.split("def _plan_step_change_impact", 1)[1].split("def _render_plan", 1)[0]
    assert "Generated configuration preview" in technical
    assert "Change impact details" in technical
    assert "technical_change_impact_table" in technical
    assert "Step ID" in technical
    assert "Technical impact" in technical
    assert "Rollback scope" in technical
    assert "_plan_file_change_detail" in technical


def test_technical_details_include_resume_grub_and_command_meaning() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    technical = source.split("def _plan_step_change_impact", 1)[1].split("def _render_plan", 1)[0]
    assert "Writes {RESUME_FILE}" in technical
    assert "Writes {GRUB_FRAGMENT}" in technical
    assert "Runs update-initramfs -u" in technical
    assert "Runs update-grub" in technical
    assert "resume=UUID" in technical
    assert "resume_offset" in technical
