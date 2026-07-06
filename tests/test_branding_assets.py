from pathlib import Path


def test_branding_assets_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / 'ubuntu_hibernate_wizard' / 'assets' / 'banner.png').exists()
    assert (root / 'ubuntu_hibernate_wizard' / 'assets' / 'icons' / 'app-icon.png').exists()
    assert (root / 'data' / 'banner.png').exists()
    assert (root / 'data' / 'icons' / 'io.github.ami3go.UbuntuHibernateWizard.png').exists()


def test_readme_uses_png_banner() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / 'README.md').read_text(encoding='utf-8')
    assert 'docs/assets/banner.png' in readme


def test_makefile_installs_png_app_icon() -> None:
    root = Path(__file__).resolve().parents[1]
    makefile = (root / 'Makefile').read_text(encoding='utf-8')
    assert 'hicolor/512x512/apps' in makefile
    assert 'io.github.ami3go.UbuntuHibernateWizard.png' in makefile
