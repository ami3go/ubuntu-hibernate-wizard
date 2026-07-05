"""CLI mode (SS27.7). Read-only, in-process; refuses mutations by design.
Exit codes: 0 = ok, 2 = mismatch, 3 = cannot check (needs root)."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from ubuntu_hibernate_wizard.core import parsers, system

ENV = {"LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}

EXIT_OK, EXIT_MISMATCH, EXIT_CANNOT_CHECK = 0, 2, 3


def _run(argv, timeout=60):
    return subprocess.run(argv, check=False, capture_output=True,
                          text=True, timeout=timeout, env=ENV)


def _find_swap_file() -> str | None:
    for d in parsers.parse_swapon_show_bytes(
            _run(["swapon", "--show", "--bytes"]).stdout):
        if d.type == "file" and d.name in ("/swap.img", "/swapfile"):
            return d.name
    return None


def verify_json() -> int:
    result: dict = {"schema_version": 1}
    swap = _find_swap_file()
    if swap is None:
        result.update(all_ok=False, errors=["no active disk swap file"])
        print(json.dumps(result, indent=2))
        return EXIT_MISMATCH
    result["swap_file"] = swap

    if os.geteuid() != 0:
        # SS27.7.3: degrade gracefully, distinct exit code
        result.update(all_ok=None, offset="unknown (needs root)",
                      errors=["run with sudo for full verification"])
        print(json.dumps(result, indent=2))
        return EXIT_CANNOT_CHECK

    try:
        _, fstype, uuid = parsers.parse_findmnt_target(
            _run(["findmnt", "-no", "SOURCE,FSTYPE,UUID", "-T", swap]).stdout)
        offset = parsers.parse_filefrag_offset(
            _run(["filefrag", "-v", swap]).stdout)
        active = [d.name for d in parsers.parse_swapon_show_bytes(
            _run(["swapon", "--show", "--bytes"]).stdout)]
        initrd = ""
        try:
            initrd = open("/etc/initramfs-tools/conf.d/resume").read()
        except FileNotFoundError:
            pass
        vr = system.verify(swap, active, uuid, offset,
                           open("/proc/cmdline").read(), initrd)
    except parsers.ParseError as e:
        result.update(all_ok=False, errors=[f"parse error: {e}"])
        print(json.dumps(result, indent=2))
        return EXIT_MISMATCH

    result.update(all_ok=vr.all_ok, errors=vr.errors,
                  fs_uuid=uuid, real_offset=offset,
                  checks={"swap": vr.active_swap_ok,
                          "uuid": vr.resume_uuid_ok,
                          "offset": vr.resume_offset_ok,
                          "initramfs": vr.initramfs_resume_ok})
    print(json.dumps(result, indent=2))
    return EXIT_OK if vr.all_ok else EXIT_MISMATCH


def guard_notify() -> int:
    """Session watcher (SS27.1.3): notify once per distinct drift."""
    from ubuntu_hibernate_wizard.state import state_manager as sm
    status = sm.load_guard_status()
    marker = os.path.join(sm.STATE_DIR, "last-notified-hash")
    last = None
    try:
        last = open(marker).read().strip()
    except FileNotFoundError:
        pass
    if not sm.should_notify(status, last):
        return 0
    subprocess.run(["notify-send", "-a", "Hibernate Wizard",
                    "-i", "io.github.example.UbuntuHibernateWizard",
                    "Hibernation configuration is out of date",
                    "Open Hibernate Wizard to repair."], check=False)
    os.makedirs(sm.STATE_DIR, exist_ok=True)
    open(marker, "w").write(sm.status_hash(status))
    return 0


def main(argv: list[str]) -> int | None:
    """Returns exit code for CLI flags, None to launch the GUI."""
    if "--verify" in argv or "--check" in argv:
        return verify_json()
    if "--guard-check" in argv:
        return guard_check()
    if "--guard-notify" in argv:
        return guard_notify()
    return None


def guard_check() -> int:
    """SS27.1 root guard: verify read-only, write status file, never modify."""
    import datetime
    import io
    from contextlib import redirect_stdout
    from ubuntu_hibernate_wizard.state import state_manager as sm
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = verify_json()
    try:
        data = json.loads(buf.getvalue())
    except json.JSONDecodeError:
        data = {"all_ok": False, "errors": ["guard: verify produced no JSON"]}
    sm.write_guard_status(bool(data.get("all_ok")), data.get("errors", []),
                          datetime.datetime.now().isoformat())
    return 0 if code == EXIT_OK else code
