from pathlib import Path


SCREENSHOTS = [
    "00_contact_sheet_all_menu_steps.png",
    "01_introduction.png",
    "02_system_check.png",
    "03_configuration.png",
    "04_planned_modifications.png",
    "05_review_apply.png",
    "06_finish.png",
]


def test_real_screenshot_assets_exist() -> None:
    base = Path("docs/assets/screenshots/menu")
    for name in SCREENSHOTS:
        path = base / name
        assert path.exists(), name
        assert path.stat().st_size > 20_000, name


def test_readme_uses_real_screenshots() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "Real application screenshots" in readme
    assert "docs/assets/screenshots/menu/00_contact_sheet_all_menu_steps.png" in readme
    assert "docs/assets/screenshots/menu/04_planned_modifications.png" in readme
    assert "0.4.3 RC4" in readme


def test_github_pages_use_real_screenshots() -> None:
    index = Path("docs/index.md").read_text(encoding="utf-8")
    screenshots = Path("docs/screenshots-and-examples.md").read_text(encoding="utf-8")
    real_page = Path("docs/real-screenshots.md").read_text(encoding="utf-8")
    assert "real GTK4 menu screens" in index
    assert "0.4.3 RC4" in screenshots
    assert "assets/screenshots/menu/05_review_apply.png" in screenshots
    assert "Real screenshots" in real_page
    assert "Real Screenshots: real-screenshots.md" in Path("mkdocs.yml").read_text(encoding="utf-8")
