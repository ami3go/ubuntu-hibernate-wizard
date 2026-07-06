from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_final_page_lists_both_gnome_extension_urls():
    src = (ROOT / "ubuntu_hibernate_wizard/ui/wizard_window.py").read_text()
    assert "https://extensions.gnome.org/extension/755/hibernate-status-button/" in src
    assert "https://extensions.gnome.org/extension/3814/system-action-hibernate/" in src
    assert "System Action - Hibernate" in src


def test_verbose_apply_log_mentions_exact_manipulations():
    src = (ROOT / "ubuntu_hibernate_wizard/backend/session.py").read_text()
    required_fragments = [
        "Selected swap target",
        "Backups for changed system files will be written to",
        "Allowed managed files",
        "update-grub",
        "update-initramfs -u",
        "Dry-run mode",
        "no system files will be written",
    ]
    for fragment in required_fragments:
        assert fragment in src


def test_privileged_helper_implements_v042_policy_and_config_steps():
    src = (ROOT / "ubuntu_hibernate_wizard/backend/privileged_helper.py").read_text()
    assert "run_one_shot" in src
    assert "apply-plan" in src
    assert "/etc/initramfs-tools/conf.d/resume" in src
    assert "/etc/default/grub.d/hibernate-wizard.cfg" in src
    assert "resize-swap" not in src.split("MUTATING", 1)[1].split("READ_ONLY", 1)[0]
