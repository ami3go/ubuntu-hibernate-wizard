from pathlib import Path


def test_application_desktop_icon_assets_are_synced() -> None:
    root = Path(__file__).resolve().parents[1]
    svg_paths = [
        root / "data" / "icons" / "io.github.ami3go.UbuntuHibernateWizard.svg",
        root / "docs" / "assets" / "app-icon.svg",
        root / "ubuntu_hibernate_wizard" / "assets" / "icons" / "app-icon.svg",
    ]
    png_paths = [
        root / "data" / "icons" / "io.github.ami3go.UbuntuHibernateWizard.png",
        root / "docs" / "assets" / "app-icon.png",
        root / "ubuntu_hibernate_wizard" / "assets" / "icons" / "app-icon.png",
    ]
    svg_texts = [p.read_text(encoding="utf-8") for p in svg_paths]
    assert all('viewBox="0 0 128 128"' in text for text in svg_texts)
    assert len(set(svg_texts)) == 1
    assert all(p.exists() and p.stat().st_size > 1024 for p in png_paths)


def test_makefile_installs_scalable_and_png_desktop_icons() -> None:
    root = Path(__file__).resolve().parents[1]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    assert "hicolor/scalable/apps" in makefile
    assert "hicolor/512x512/apps" in makefile
    assert "io.github.ami3go.UbuntuHibernateWizard.svg" in makefile
    assert "io.github.ami3go.UbuntuHibernateWizard.png" in makefile
