from pathlib import Path


def test_exact_runtime_diagram_asset_is_still_bundled_for_docs_or_later_reuse() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "ubuntu_hibernate_wizard" / "assets" / "runtime-hibernation-resume.png").exists()
    assert (root / "docs" / "assets" / "runtime-hibernation-resume.png").exists()


def test_intro_no_long_runtime_diagram_card() -> None:
    source = Path("ubuntu_hibernate_wizard/ui/wizard_window.py").read_text(encoding="utf-8")
    intro = source.split("def _intro_page", 1)[1].split("def _check_page", 1)[0]
    assert "Runtime hibernation / resume diagram" not in intro
    assert "self._runtime_diagram_picture()" not in intro
