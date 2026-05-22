"""Sandbox backends for shell command execution.

To add a new backend, implement a function with the signature:
    _wrap_<name>(command: str, workspace: str, cwd: str) -> str
and register it in _BACKENDS below.
"""

import shlex
from pathlib import Path

from nanobot.agent.tools.sandbox_setuid import parse_setuid_sandbox, wrap_setuid
from nanobot.config.paths import get_media_dir


def _sandbox_cwd(workspace: str, cwd: str) -> str:
    ws = Path(workspace).resolve()
    try:
        return str(ws / Path(cwd).resolve().relative_to(ws))
    except ValueError:
        return str(ws)


def _bwrap(command: str, workspace: str, cwd: str) -> str:
    """Wrap command in a bubblewrap sandbox (requires bwrap in container).

    Only the workspace is bind-mounted read-write; its parent dir (which holds
    config.json) is hidden behind a fresh tmpfs.  The media directory is
    bind-mounted read-only so exec commands can read uploaded attachments.
    """
    ws = Path(workspace).resolve()
    media = get_media_dir().resolve()

    sandbox_cwd = _sandbox_cwd(workspace, cwd)

    required  = ["/usr"]
    optional  = ["/bin", "/lib", "/lib64", "/etc/alternatives",
                 "/etc/ssl/certs", "/etc/resolv.conf", "/etc/ld.so.cache"]

    args = ["bwrap", "--new-session", "--die-with-parent"]
    for p in required:
        args += ["--ro-bind", p, p]
    for p in optional:
        args += ["--ro-bind-try", p, p]
    args += [
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--tmpfs", str(ws.parent),        # mask config dir
        "--dir", str(ws),                 # recreate workspace mount point
        "--bind", str(ws), str(ws),
        "--ro-bind-try", str(media), str(media),  # read-only access to media
        "--chdir", sandbox_cwd,
        "--", "sh", "-c", command,
    ]
    return shlex.join(args)


_BACKENDS = {"bwrap": _bwrap}
_BACKEND_NAMES = [*_BACKENDS, "setuid", "setuid:<uid>", "setuid:<uid>:<gid>"]


def wrap_command(sandbox: str, command: str, workspace: str, cwd: str) -> str:
    """Wrap *command* using the named sandbox backend."""
    if setuid_spec := parse_setuid_sandbox(sandbox):
        return wrap_setuid(command, workspace, cwd, setuid_spec)
    if backend := _BACKENDS.get(sandbox):
        return backend(command, workspace, cwd)
    raise ValueError(f"Unknown sandbox backend {sandbox!r}. Available: {_BACKEND_NAMES}")
