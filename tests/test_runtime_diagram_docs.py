from pathlib import Path


def test_runtime_diagram_documents_all_8_steps_and_touchpoints():
    text = Path("docs/how-hibernation-works.md").read_text(encoding="utf-8")
    for step in [
        "1. Launch and privilege check",
        "2. System discovery",
        "3. Swap target classification",
        "4. Safety decision",
        "5. Generate dry-run plan",
        "6. Apply with backup and rollback metadata",
        "7. Verify configuration",
        "8. Diagnostic ZIP and rollback path",
    ]:
        assert step in text
    for touchpoint in [
        "/proc/swaps",
        "/proc/meminfo",
        "/etc/fstab",
        "/etc/crypttab",
        "/etc/default/grub",
        "/sys/power/state",
        "/sys/power/resume",
        "lsblk",
        "findmnt",
        "swapon --show",
        "dmsetup info",
        "filefrag",
    ]:
        assert touchpoint in text


def test_spec_explicitly_allows_python_built_gtk_widgets():
    text = Path("spec/ubuntu_hibernate_wizard_task.md").read_text(encoding="utf-8")
    assert "GTK/libadwaita UI may be built programmatically in Python" in text
