from pathlib import Path


def test_review_apply_page_has_back_button_and_plain_plan_review() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    assert "btn_back_plan" in source
    assert "Back to Planned Modifications" in source
    assert "apply_review_plan" in source
    assert "Review planned changes" in source
    assert "Plain numbered summary" in source
    assert "apply_review_target" not in source
    assert "Review selected target" not in source


def test_review_apply_plain_text_has_numbered_steps_and_metadata_sections() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    review_section = source.split("def _append_apply_review", 1)[1].split("def _apply_page", 1)[0]
    assert "for idx, step in enumerate(self.plan.steps, start=1)" in review_section
    assert 'lines.append(f"{idx}. {step.title}{detail}")' in review_section
    assert "Blocking reasons:" in review_section
    assert "Warnings:" in review_section
    assert "Managed files:" in review_section
    assert "self._label(review_text, monospace=True)" in review_section
