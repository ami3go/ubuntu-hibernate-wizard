from pathlib import Path


def test_finish_export_log_button_is_in_same_ui_element_as_status_text() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    finish = source.split("def _finish_page", 1)[1].split("def _help_page", 1)[0]
    assert 'export_card = self._card("Export log"' in finish
    assert 'export_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL' in finish
    assert 'export_row.append(self._finish_export_status)' in finish
    assert 'export_row.append(export_log_btn)' in finish
    assert 'export_card.append(export_row)' in finish
    assert 'box.append(self._button_row(verify_btn, rollback_btn))' in finish
    assert 'box.append(self._button_row(verify_btn, export_log_btn, rollback_btn))' not in finish
