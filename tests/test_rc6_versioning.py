from pathlib import Path


def test_rc6_user_visible_version() -> None:
    assert 'APP_VERSION = "0.4.3-rc6"' in Path("ubuntu_hibernate_wizard/constants.py").read_text(encoding="utf-8")
    assert '__version__ = "0.4.3rc6"' in Path("ubuntu_hibernate_wizard/__init__.py").read_text(encoding="utf-8")
    assert 'version = "0.4.3rc6"' in Path("pyproject.toml").read_text(encoding="utf-8")


def test_rc6_debian_versioning() -> None:
    assert "VERSION  := 0.4.3~rc6-1" in Path("Makefile").read_text(encoding="utf-8")
    assert "ubuntu-hibernate-wizard (0.4.3~rc6-1)" in Path("packaging/changelog.Debian").read_text(encoding="utf-8")


def test_rc6_release_notes_exist() -> None:
    notes = Path("docs/release-0.4.3-rc6.md").read_text(encoding="utf-8")
    assert "0.4.3 RC6" in notes
    assert "free-space preflight" in notes
