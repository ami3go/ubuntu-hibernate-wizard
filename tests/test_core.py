"""Test suite per spec §12 + §22 acceptance fixture + §26.2 journal recovery."""
import pytest

from ubuntu_hibernate_wizard.core.parsers import (
    ParseError, parse_filefrag_offset, parse_swapon_show_bytes,
    parse_findmnt_target, parse_cmdline_resume, resume_uuid, validate_uuid)
from ubuntu_hibernate_wizard.core.grub import (
    set_resume_params, read_default_cmdline, GrubEditError)
from ubuntu_hibernate_wizard.core.system import (
    ensure_swap_entry, verify, ResizeJournal, recovery_action,
    make_manifest, rollback_plan, BackupEntry)

UUID = "d76e67b3-404f-461e-a961-7963664d66b3"

# ------------------------------------------------ filefrag (§12.3, .16, .17, §20.4)
FRAG_OK = """Filesystem type is: ef53
File size of /swap.img is 24576000000 (6000000 blocks of 4096 bytes)
 ext:     logical_offset:        physical_offset: length:   expected: flags:
   0:        0..    32767:    5986304..   6019071:  32768:
"""

@pytest.mark.parametrize("field", ["5986304..", "5986304:", "5986304 "])
def test_filefrag_field_styles(field):
    line = f"   0:        0..    32767:    {field}   6019071:  32768:\n"
    assert parse_filefrag_offset(line) == 5986304

def test_filefrag_full_output():
    assert parse_filefrag_offset(FRAG_OK) == 5986304

@pytest.mark.parametrize("bad", [
    "   0:        0..    32767:    unknown..    6019071:  32768:",
    "Filesystem type is: ef53",
    "/swap.img: 0 extents found",
    "",
])
def test_filefrag_rejects_invalid(bad):
    with pytest.raises(ParseError):
        parse_filefrag_offset(bad)

# ------------------------------------------------ swapon (§12.1, .4, .5)
SWAPON = "NAME       TYPE SIZE USED PRIO\n/swap.img  file 24576000000 0 -1\n"
SWAPON_ZRAM = "NAME       TYPE      SIZE USED PRIO\n/dev/zram0 partition 8589934592 0 100\n"

def test_swapon_parse_and_detect_file():
    devs = parse_swapon_show_bytes(SWAPON)
    assert devs[0].name == "/swap.img" and devs[0].type == "file"
    assert devs[0].size_bytes == 24576000000

def test_swapon_zram_only_detected():
    devs = parse_swapon_show_bytes(SWAPON_ZRAM)
    assert all(d.is_zram for d in devs)

def test_swapon_empty_ok():
    assert parse_swapon_show_bytes("") == []

# ------------------------------------------------ findmnt (§12.2, .6)
def test_findmnt_parse():
    src, fs, uu = parse_findmnt_target(f"/dev/nvme0n1p2 ext4 {UUID}\n")
    assert (src, fs, uu) == ("/dev/nvme0n1p2", "ext4", UUID)

def test_findmnt_btrfs_detected_as_unsupported_fstype():
    _, fs, _ = parse_findmnt_target(f"/dev/sda2 btrfs {UUID}\n")
    assert fs != "ext4"  # caller must hard-stop (§3)

def test_uuid_validation():
    with pytest.raises(ParseError):
        validate_uuid("not-a-uuid")

# ------------------------------------------------ GRUB (§12.7, .8, .14, .15, §20.3)
@pytest.mark.parametrize("line", [
    'GRUB_CMDLINE_LINUX_DEFAULT=""',
    'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"',
    'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash resume=OLD resume_offset=999"',
    "GRUB_CMDLINE_LINUX_DEFAULT='quiet splash'",
    'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash resume=UUID=old resume_offset=30091264"',
])
def test_grub_rewrite_all_forms(line):
    text = f"# comment\n{line}\nGRUB_CMDLINE_LINUX=\"console=ttyS0\"\n"
    out = set_resume_params(text, UUID, 5986304)
    val = read_default_cmdline(out)
    assert f"resume=UUID={UUID}" in val and "resume_offset=5986304" in val
    assert val.count("resume_offset=") == 1 and "OLD" not in val
    assert 'GRUB_CMDLINE_LINUX="console=ttyS0"' in out      # unrelated var kept
    assert "# comment" in out                                # comments kept

def test_grub_preserves_quiet_splash():
    out = set_resume_params('GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\n',
                            UUID, 5986304)
    assert read_default_cmdline(out).startswith("quiet splash ")

def test_grub_noresume_kept_by_default_removed_on_plan():
    src = 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash noresume"\n'
    assert "noresume" in read_default_cmdline(set_resume_params(src, UUID, 1))
    assert "noresume" not in read_default_cmdline(
        set_resume_params(src, UUID, 1, remove_noresume=True))

def test_grub_missing_var_needs_approval():
    with pytest.raises(GrubEditError):
        set_resume_params("GRUB_TIMEOUT=5\n", UUID, 1)
    out = set_resume_params("GRUB_TIMEOUT=5\n", UUID, 1, allow_add_line=True)
    assert "GRUB_CMDLINE_LINUX_DEFAULT=" in out

# ------------------------------------------------ fstab (§12.9, Q3 idempotency)
def test_fstab_add_and_idempotent():
    base = "UUID=abc / ext4 defaults 0 1\n"
    out, changed = ensure_swap_entry(base, "/swap.img")
    assert changed and "/swap.img none swap sw 0 0" in out
    out2, changed2 = ensure_swap_entry(out, "/swap.img")
    assert not changed2 and out2 == out          # apply twice -> no change

def test_fstab_ignores_commented_entry():
    base = "#/swap.img none swap sw 0 0\n"
    out, changed = ensure_swap_entry(base, "/swap.img")
    assert changed and out.count("/swap.img none swap sw 0 0") == 2 - 1 + 1  # comment + real

# ------------------------------------------------ verification (§12.10, .11, §22)
CMDLINE_STALE = (f"BOOT_IMAGE=/vmlinuz root=UUID={UUID} ro quiet splash "
                 f"resume=UUID={UUID} resume_offset=30091264")
INITRD_OK = f"RESUME=UUID={UUID} resume_offset=5986304\n"

def test_acceptance_fixture_section_22():
    """The real-world bug: UUID pass, offset fail, correct repair values."""
    r = verify("/swap.img", ["/swap.img"], UUID, 5986304,
               CMDLINE_STALE, INITRD_OK)
    assert r.active_swap_ok and r.resume_uuid_ok
    assert not r.resume_offset_ok and not r.all_ok
    assert any("30091264" in e and "5986304" in e for e in r.errors)

def test_verification_all_pass():
    cmd = CMDLINE_STALE.replace("30091264", "5986304")
    r = verify("/swap.img", ["/swap.img"], UUID, 5986304, cmd, INITRD_OK)
    assert r.all_ok and r.errors == []

def test_cmdline_parser():
    p = parse_cmdline_resume(CMDLINE_STALE)
    assert resume_uuid(p) == UUID and p.resume_offset == 30091264

def test_cmdline_rejects_bad_offset():
    with pytest.raises(ParseError):
        parse_cmdline_resume("resume_offset=abc")

# ------------------------------------------------ journal recovery (§12.23, §26.2)
@pytest.mark.parametrize("phase,side,expect", [
    ("building",  True,  "delete_side_restart"),
    ("switching", True,  "reactivate_old_delete_side"),
    ("switching", False, "activate_new_continue"),
    ("activated", False, "resume_reconfigure"),
])
def test_journal_recovery_table(phase, side, expect):
    j = ResizeJournal("/swap.img", "/swap.img.new", 1 << 30, phase)
    assert recovery_action(j, side_exists=side, target_exists=True) == expect

def test_journal_stray_side_reported():
    assert recovery_action(None, side_exists=True, target_exists=True) \
        == "report_stray_side"

def test_journal_roundtrip(tmp_path):
    p = str(tmp_path / "j.json")
    ResizeJournal("/swap.img", "/swap.img.new", 42, "building").save(p)
    j = ResizeJournal.load(p)
    assert j.phase == "building" and j.size_bytes == 42
    ResizeJournal.clear(p)
    assert ResizeJournal.load(p) is None

def test_journal_corrupt_not_fatal(tmp_path):
    p = tmp_path / "j.json"; p.write_text("{broken")
    assert ResizeJournal.load(str(p)).phase == "corrupt"

# ------------------------------------------------ backup/rollback (§12.12, .13)
def test_manifest_and_rollback_plan():
    m = make_manifest([BackupEntry("/etc/default/grub", "grub", True),
                       BackupEntry("/etc/initramfs-tools/conf.d/resume", None, False)],
                      "2026-07-05T12:00:00+03:00")
    plan = rollback_plan(m)
    assert ("restore", "/etc/default/grub", "grub") in plan
    assert ("remove", "/etc/initramfs-tools/conf.d/resume", None) in plan
