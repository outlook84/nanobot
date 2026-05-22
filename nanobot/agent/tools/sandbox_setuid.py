"""setpriv-based sandbox backend for rootless container deployments."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_UID = 1001
_DEFAULT_GID = 1001
_MAX_ID = 2_147_483_647
_SPEC_RE = re.compile(r"^setuid(?::(?P<uid>\d+)(?::(?P<gid>\d+))?)?$")


@dataclass(frozen=True, slots=True)
class SetuidSandboxSpec:
    uid: int
    gid: int


def parse_setuid_sandbox(sandbox: str) -> SetuidSandboxSpec | None:
    """Parse setuid sandbox names: setuid, setuid:<uid>, setuid:<uid>:<gid>."""
    match = _SPEC_RE.fullmatch(sandbox)
    if not match:
        return None

    uid_text = match.group("uid")
    gid_text = match.group("gid")
    uid = int(uid_text or _DEFAULT_UID)
    gid = int(gid_text or (uid_text if uid_text is not None else _DEFAULT_GID))
    if uid == 0 or gid == 0:
        raise ValueError("setuid sandbox UID/GID must be non-root")
    if uid > _MAX_ID or gid > _MAX_ID:
        raise ValueError(f"setuid sandbox UID/GID must be between 1 and {_MAX_ID}")
    return SetuidSandboxSpec(uid=uid, gid=gid)


def _sandbox_cwd(workspace: str, cwd: str) -> str:
    ws = Path(workspace).resolve()
    try:
        return str(ws / Path(cwd).resolve().relative_to(ws))
    except ValueError:
        return str(ws)


def wrap_setuid(
    command: str,
    workspace: str,
    cwd: str,
    spec: SetuidSandboxSpec,
) -> str:
    """Wrap command with setpriv-based UID/GID drop.

    This backend is intended for deployments where nanobot itself runs as UID 0
    inside a rootless container. The target UID/GID are numeric on purpose: the
    image does not need an /etc/passwd entry or home directory for the exec user.
    """
    ws = Path(workspace).resolve()
    sandbox_cwd = _sandbox_cwd(workspace, cwd)
    venv = ws / ".venv"
    ws_shell = shlex.quote(str(ws))
    venv_python = shlex.quote(str(venv / "bin" / "python"))
    venv_bin = shlex.quote(str(venv / "bin"))
    venv_dir = shlex.quote(str(venv))

    workspace_error = shlex.quote(
        f"Error: setuid sandbox workspace is not writable by exec UID/GID "
        f"{spec.uid}:{spec.gid}: {ws}"
    )
    workspace_fix = shlex.quote(
        f"Fix: adjust the host bind-mount ownership so exec UID/GID "
        f"{spec.uid}:{spec.gid} can write the workspace"
    )
    venv_error = shlex.quote(
        f"Error: setuid sandbox venv path is not writable by exec UID/GID "
        f"{spec.uid}:{spec.gid}: {venv}"
    )
    venv_fix = shlex.quote(
        f"Fix: remove the workspace .venv or adjust its host ownership for "
        f"exec UID/GID {spec.uid}:{spec.gid}"
    )
    bootstrap_error = shlex.quote(
        f"Error: failed to create workspace venv as exec UID/GID {spec.uid}:{spec.gid}: {venv}"
    )

    preflight = (
        f"if [ ! -w {ws_shell} ]; then "
        f"echo {workspace_error} >&2; echo {workspace_fix} >&2; exit 126; "
        "fi"
        f" && if [ -e {venv_dir} ] && [ ! -w {venv_dir} ]; then "
        f"echo {venv_error} >&2; echo {venv_fix} >&2; exit 126; "
        "fi"
    )
    bootstrap_venv = (
        f"if [ ! -x {venv_python} ]; then "
        f"python -m venv {venv_dir} || "
        f"(echo {bootstrap_error} >&2; exit 126); "
        "fi"
        f' && export PATH={venv_bin}:"$PATH"'
    )
    args = [
        "env", f"HOME={ws}",
        "setpriv",
        "--reuid", str(spec.uid),
        "--regid", str(spec.gid),
        "--clear-groups",
        "--inh-caps=-all,+net_raw",
        "--ambient-caps=-all,+net_raw",
        "--bounding-set=-all,+net_raw",
        "--no-new-privs",
        "--",
        "sh", "-c", f"cd {shlex.quote(sandbox_cwd)} && {preflight} && {bootstrap_venv} && {command}",
    ]
    return shlex.join(args)
