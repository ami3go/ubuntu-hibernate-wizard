from pathlib import Path


def test_finish_page_has_inline_export_log_button() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    finish_section = source.split("def _finish_page", 1)[1].split("def _help_page", 1)[0]
    assert '"Export log"' in finish_section
    assert '"Export apply log"' not in finish_section
    assert 'Gtk.Button(label="Export log")' in finish_section
    assert "btn_export_log" in finish_section
    assert "btn_export_apply_log" not in finish_section
    assert "export_row.append(self._finish_export_status)" in finish_section
    assert "export_row.append(export_log_btn)" in finish_section
    assert "self._button_row(verify_btn, rollback_btn)" in finish_section
