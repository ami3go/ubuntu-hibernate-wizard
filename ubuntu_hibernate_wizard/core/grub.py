"""GRUB_CMDLINE_LINUX_DEFAULT editor (§20.3). Pure functions, no I/O."""
from __future__ import annotations

import re

_LINE = re.compile(
    r'^(?P<lead>\s*)GRUB_CMDLINE_LINUX_DEFAULT=(?P<q>["\'])(?P<val>.*)(?P=q)\s*$'
)


class GrubEditError(ValueError):
    pass


def _rewrite_params(value: str, uuid: str, offset: int, remove_noresume: bool) -> str:
    tokens = value.split()
    kept = []
    for t in tokens:
        if t.startswith("resume=") or t.startswith("resume_offset="):
            continue  # always replaced (§20.3)
        if t == "noresume":
            if remove_noresume:
                continue
            kept.append(t)
            continue
        kept.append(t)
    kept += [f"resume=UUID={uuid}", f"resume_offset={offset}"]
    return " ".join(kept)


def set_resume_params(grub_text: str, uuid: str, offset: int,
                      remove_noresume: bool = False,
                      allow_add_line: bool = False) -> str:
    """Return new /etc/default/grub content with resume params set.

    - Edits only GRUB_CMDLINE_LINUX_DEFAULT.
    - Preserves unrelated params, variables, and comments.
    - Removes old resume=/resume_offset= before adding new values.
    - Removes `noresume` only when remove_noresume=True (approved plan).
    - Adds the variable only when allow_add_line=True (user approval, §20.3).
    """
    if offset <= 0:
        raise GrubEditError(f"invalid offset {offset}")
    out_lines = []
    found = False
    for line in grub_text.splitlines():
        m = _LINE.match(line)
        if m and not found:
            found = True
            newval = _rewrite_params(m.group("val"), uuid, offset, remove_noresume)
            out_lines.append(f'{m.group("lead")}GRUB_CMDLINE_LINUX_DEFAULT="{newval}"')
        else:
            out_lines.append(line)
    if not found:
        if not allow_add_line:
            raise GrubEditError("GRUB_CMDLINE_LINUX_DEFAULT missing; "
                                "adding it requires explicit approval")
        out_lines.append(
            f'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash '
            f'resume=UUID={uuid} resume_offset={offset}"')
    result = "\n".join(out_lines)
    if grub_text.endswith("\n"):
        result += "\n"
    return result


def read_default_cmdline(grub_text: str) -> str | None:
    for line in grub_text.splitlines():
        m = _LINE.match(line)
        if m:
            return m.group("val")
    return None
