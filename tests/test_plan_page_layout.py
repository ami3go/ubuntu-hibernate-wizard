from pathlib import Path


def test_planned_modifications_uses_compact_dashboard_without_safety_card() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    plan_page = source.split("def _plan_page", 1)[1].split("def _render_plan", 1)[0]
    assert "Status summary" in plan_page
    assert "Planned changes" in plan_page
    assert "Technical details" in plan_page
    assert "Gtk.Expander" in plan_page
    assert "Back to Configuration" in plan_page
    assert "Continue to Review & Apply" in plan_page
    assert "Safety" not in plan_page
    assert "plan_safety_compact" not in plan_page
    assert "Apply phase" not in plan_page
    assert "Runtime hibernation cycle" not in plan_page
    assert "apply_phase_diagram" not in plan_page


def test_plan_renderer_uses_status_changes_and_collapsed_details() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    render_helpers = source.split("def _compact_status_table", 1)[1].split("def _format_plan_target_detail", 1)[0]
    assert "_plan_add_status_summary" in render_helpers
    assert "_plan_add_short_changes" in render_helpers
    assert "_plan_add_technical_details" in render_helpers
    assert "_plan_add_safety_checklist" not in render_helpers
    assert "Resume UUID" in render_helpers
    assert "Resume offset" in render_helpers
    assert "Rollback backup location" in render_helpers


def test_status_summary_uses_table_layout() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    assert "def _compact_status_table" in source
    assert "compact_status_table" in source
    assert "Field" in source
    assert "Value" in source
