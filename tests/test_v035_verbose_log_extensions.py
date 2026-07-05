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
        "resume=UUID=",
        "resume_offset=",
        "update-grub",
        "update-initramfs -u -k all",
        "systemd sleep override",
        "polkit logind hibernate rule",
    ]
    for fragment in required_fragments:
        assert fragment in src


def test_privileged_helper_implements_policy_and_config_steps():
    src = (ROOT / "ubuntu_hibernate_wizard/backend/privileged_helper.py").read_text()
    assert "def cmd_update_fstab" in src
    assert "def cmd_update_sleep_conf" in src
    assert "def cmd_update_polkit_rule" in src
    assert "/etc/systemd/sleep.conf.d/99-ubuntu-hibernate-wizard.conf" in src
    assert "/etc/polkit-1/rules.d/49-ubuntu-hibernate-wizard.rules" in src
    assert "org.freedesktop.login1.hibernate" in src
