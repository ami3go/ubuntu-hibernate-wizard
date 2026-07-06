#!/usr/bin/env python3
"""Generate deterministic Rev-B fake-system fixtures and golden outputs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ubuntu_hibernate_wizard.services.hibernate_planner import build_modification_plan
from ubuntu_hibernate_wizard.services.system_probe import load_fake_system_data, profile_from_probe_data

ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "fake_systems"
UUID1 = "d76e67b3-404f-461e-a961-7963664d66b3"
UUID2 = "aaaaaaaa-404f-461e-a961-7963664d66b3"
PARTUUID = "11111111-2222-3333-4444-555555555555"
RAM = 8 * 1024 ** 3
BIG = 16 * 1024 ** 3
SMALL = 4 * 1024 ** 3
MEMINFO = "MemTotal:        8388608 kB\n"
POWER = "freeze mem disk\n"
FSTAB = f"UUID={UUID2} / ext4 defaults 0 1\n"
GRUB = 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\n'
OS_RELEASE = 'ID=ubuntu\nPRETTY_NAME="Ubuntu fixture"\n'


def base_files(path: Path, *, crypttab: str = "", root: str = f"/dev/disk/by-uuid/{UUID2} ext4 {UUID2}\n"):
    (path / "files").mkdir(parents=True, exist_ok=True)
    (path / "commands").mkdir(exist_ok=True)
    (path / "expected").mkdir(exist_ok=True)
    (path / "files/proc-meminfo.txt").write_text(MEMINFO, encoding="utf-8")
    (path / "files/sys-power-state.txt").write_text(POWER, encoding="utf-8")
    (path / "files/sys-power-resume.txt").write_text("0:0\n", encoding="utf-8")
    (path / "files/etc-fstab.txt").write_text(FSTAB, encoding="utf-8")
    (path / "files/etc-crypttab.txt").write_text(crypttab, encoding="utf-8")
    (path / "files/etc-default-grub.txt").write_text(GRUB, encoding="utf-8")
    (path / "files/etc-os-release.txt").write_text(OS_RELEASE, encoding="utf-8")
    (path / "commands/findmnt-root.txt").write_text(root, encoding="utf-8")
    (path / "fixture.json").write_text(json.dumps({
        "ram_bytes": RAM,
        "bootloader": "grub",
        "initramfs": "initramfs-tools",
        "distro": "ubuntu",
        "distro_version": "Ubuntu fixture",
    }, indent=2), encoding="utf-8")


def write_lsblk(path: Path, devices: list[dict]):
    (path / "commands/lsblk.json").write_text(json.dumps({"blockdevices": devices}, indent=2), encoding="utf-8")


def write_dm(path: Path, text: str = ""):
    (path / "commands/dmsetup-info.txt").write_text(text, encoding="utf-8")


def write_swap(path: Path, rows: list[tuple[str, str, int, int, int]], details: dict):
    header = "NAME TYPE SIZE USED PRIO\n"
    body = "".join(f"{name} {typ} {size} {used} {prio}\n" for name, typ, size, used, prio in rows)
    (path / "commands/swapon-show.txt").write_text(header + body, encoding="utf-8")
    proc_body = "Filename\t\t\t\tType\t\tSize\tUsed\tPriority\n"
    for name, typ, size, used, prio in rows:
        proc_body += f"{name}\t\t\t\t{typ}\t\t{size // 1024}\t{used // 1024}\t{prio}\n"
    (path / "files/proc-swaps.txt").write_text(proc_body, encoding="utf-8")
    (path / "commands/swap-details.json").write_text(json.dumps(details, indent=2, sort_keys=True), encoding="utf-8")


def scenario(name: str, rows, details, *, crypttab="", lsblk=None, dm="", root=None, readme=""):
    p = ROOT / name
    if p.exists():
        for child in sorted(p.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
    p.mkdir(parents=True, exist_ok=True)
    base_files(p, crypttab=crypttab, root=root or f"/dev/disk/by-uuid/{UUID2} ext4 {UUID2}\n")
    write_swap(p, rows, details)
    write_lsblk(p, lsblk or [])
    write_dm(p, dm)
    (p / "README.md").write_text(readme or f"# {name}\n\nGenerated fake-system fixture for production-readiness tests.\n", encoding="utf-8")
    return p


def write_expected(p: Path):
    data = load_fake_system_data(p)
    profile = profile_from_probe_data(data)
    targets = [c.to_dict() for c in profile.candidates]
    blockers = profile.blocking_reasons
    warnings = []
    for c in profile.candidates:
        warnings.extend(c.warnings)
    plan_data = {"available": False, "can_apply": False, "blocking_reasons": blockers}
    if profile.recommended_target:
        plan = build_modification_plan(profile, profile.recommended_target)
        plan_data = {
            "available": True,
            "can_apply": plan.can_apply,
            "selected_target": plan.selected_target.path,
            "steps": [s.id for s in plan.steps],
            "planned_files": plan.planned_files,
            "warnings": plan.warnings,
            "blocking_reasons": plan.blocking_reasons,
        }
    (p / "expected/swap-targets.json").write_text(json.dumps(targets, indent=2, sort_keys=True), encoding="utf-8")
    (p / "expected/blockers.json").write_text(json.dumps(blockers, indent=2, sort_keys=True), encoding="utf-8")
    (p / "expected/warnings.json").write_text(json.dumps(warnings, indent=2, sort_keys=True), encoding="utf-8")
    (p / "expected/plan.json").write_text(json.dumps(plan_data, indent=2, sort_keys=True), encoding="utf-8")
    (p / "expected/diagnostic-summary.txt").write_text("\n".join([
        f"fixture={p.name}",
        f"targets={len(targets)}",
        f"recommended={(profile.recommended_target.path if profile.recommended_target else 'none')}",
        "blockers=" + "; ".join(blockers or ["none"]),
        "classifications=" + ", ".join(t.get("classification", "unknown") for t in targets),
    ]) + "\n", encoding="utf-8")


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    scenarios = []
    scenarios.append(scenario("swapfile_ok", [("/swap.img", "file", BIG, 0, -1)], {"/swap.img": {"filesystem": "ext4", "uuid": UUID1, "resume_offset": 5986304}}))
    scenarios.append(scenario("swapfile_too_small", [("/swap.img", "file", SMALL, 0, -1)], {"/swap.img": {"filesystem": "ext4", "uuid": UUID1, "resume_offset": 5986304}}))
    scenarios.append(scenario("swap_partition_ok", [("/dev/nvme0n1p3", "partition", BIG, 0, -2)], {"/dev/nvme0n1p3": {"uuid": UUID1, "partuuid": PARTUUID}}, lsblk=[{"name":"nvme0n1p3","kname":"nvme0n1p3","type":"part","fstype":"swap","uuid":UUID1,"partuuid":PARTUUID}]))
    scenarios.append(scenario("swap_partition_too_small", [("/dev/nvme0n1p3", "partition", SMALL, 0, -2)], {"/dev/nvme0n1p3": {"uuid": UUID1, "partuuid": PARTUUID}}))
    scenarios.append(scenario("swapfile_and_partition", [("/swap.img", "file", BIG, 0, -1), ("/dev/nvme0n1p3", "partition", BIG, 0, -2)], {"/swap.img": {"filesystem":"ext4","uuid":UUID2,"resume_offset":123456}, "/dev/nvme0n1p3": {"uuid":UUID1,"partuuid":PARTUUID}}))
    scenarios.append(scenario("no_swap", [], {}))
    crypt = "cryptswap UUID={} /dev/urandom swap,cipher=aes-xts-plain64,size=256\n".format(UUID1)
    scenarios.append(scenario("encrypted_swap_crypttab_random_key", [("/dev/mapper/cryptswap", "partition", BIG, 0, -2)], {"/dev/mapper/cryptswap": {"uuid": UUID1}}, crypttab=crypt, dm="cryptswap CRYPT-LUKS1-abc dm-0\n"))
    crypt2 = "cryptswap UUID={} /crypto-key luks\n".format(UUID1)
    scenarios.append(scenario("encrypted_swap_crypttab_named_mapper", [("/dev/mapper/cryptswap", "partition", BIG, 0, -2)], {"/dev/mapper/cryptswap": {"uuid": UUID1}}, crypttab=crypt2, dm="cryptswap CRYPT-LUKS1-abc dm-0\n"))
    scenarios.append(scenario("encrypted_swap_mapper_active", [("/dev/mapper/cryptswap", "partition", BIG, 0, -2)], {"/dev/mapper/cryptswap": {"uuid": UUID1}}, dm="cryptswap CRYPT-LUKS1-abc dm-0\n"))
    scenarios.append(scenario("encrypted_swap_unknown_mapper", [("/dev/mapper/swap0", "partition", BIG, 0, -2)], {"/dev/mapper/swap0": {"uuid": UUID1}}, dm=""))
    scenarios.append(scenario("encrypted_root_plain_swapfile", [("/swap.img", "file", BIG, 0, -1)], {"/swap.img": {"filesystem":"ext4","uuid":UUID1,"resume_offset":5986304}}, root="/dev/mapper/cryptroot ext4 {}\n".format(UUID2)))
    scenarios.append(scenario("zram_only", [("/dev/zram0", "partition", BIG, 0, 100)], {"/dev/zram0": {}}))
    scenarios.append(scenario("btrfs_swapfile", [("/swap.img", "file", BIG, 0, -1)], {"/swap.img": {"filesystem":"btrfs","uuid":UUID1,"resume_offset":222222}}))
    scenarios.append(scenario("missing_resume_config", [("/swap.img", "file", BIG, 0, -1)], {"/swap.img": {"filesystem":"ext4","uuid":UUID1,"resume_offset":5986304}}))
    scenarios.append(scenario("malformed_fstab", [("/swap.img", "file", BIG, 0, -1)], {"/swap.img": {"filesystem":"ext4","uuid":UUID1,"resume_offset":5986304}}))
    (scenarios[-1] / "files/etc-fstab.txt").write_text("this is not a valid fstab line\n", encoding="utf-8")
    scenarios.append(scenario("malformed_crypttab", [("/dev/mapper/swap0", "partition", BIG, 0, -2)], {"/dev/mapper/swap0": {"uuid": UUID1}}, crypttab="broken_line_only\n"))
    scenarios.append(scenario("read_only_filesystem", [("/swap.img", "file", BIG, 0, -1)], {"/swap.img": {"filesystem":"ext4","uuid":UUID1,"resume_offset":5986304}}))
    (scenarios[-1] / "fixture.json").write_text(json.dumps({"ram_bytes": RAM, "bootloader": "grub", "initramfs": "initramfs-tools", "read_only_config": True}, indent=2), encoding="utf-8")
    scenarios.append(scenario("dmsetup_unavailable", [("/dev/mapper/swap0", "partition", BIG, 0, -2)], {"/dev/mapper/swap0": {"uuid": UUID1}}, dm=""))
    for p in scenarios:
        write_expected(p)
    print(f"generated {len(scenarios)} fake-system fixtures under {ROOT}")


if __name__ == "__main__":
    main()
