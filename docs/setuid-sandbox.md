# Setuid Exec Sandbox

This is an optional rootless-container sandbox model for shell exec commands.
It is separate from the default Docker and bwrap deployment docs to keep the
common path stable.

## Model

Run nanobot as UID 0 inside a rootless container, then drop each exec command to
a lower numeric UID/GID with `setpriv`.

This does not start a second container for every command. Container UID 0 is
root only inside the rootless user namespace; exec commands run as the numeric
UID/GID configured in `tools.exec.sandbox`.

This backend is a UID/GID drop sandbox, not a mount namespace sandbox. It does
not provide the same filesystem isolation as `bwrap`: readable container paths
outside the workspace may still be readable to the lowered UID/GID. Nanobot
therefore treats `setuid:*` exec mode as workspace-restricted even if
`tools.restrictToWorkspace` is omitted.

## Configuration

```json
{
  "tools": {
    "restrictToWorkspace": true,
    "exec": {
      "sandbox": "setuid:1001:1001"
    }
  }
}
```

Supported forms:

- `"setuid"` uses `1001:1001`
- `"setuid:<uid>"` uses `<uid>:<uid>`
- `"setuid:<uid>:<gid>"` uses the explicit UID/GID pair

UID and GID values must be non-root numeric IDs.

Exec commands do not preserve Linux capabilities. This keeps the backend
compatible with rootless container runtimes that reject capability changes, but
means tools that require raw sockets, such as some `ping` variants, may not work.

## Build

```bash
podman build -f Dockerfile.setuid -t nanobot:setuid .
```

`Dockerfile.setuid` uses Alpine, builds WebUI static assets in a Bun stage, and
keeps the runtime image free of Node/Bun. It includes both `setpriv` and
`bubblewrap`, so the image can run either `setuid:*` or `bwrap` sandbox modes.

## Workspace Ownership

Prepare bind-mounted workspace ownership from the host. The numeric UID/GID
must match the values in `tools.exec.sandbox`.

```bash
mkdir -p ~/.nanobot/workspace
podman unshare chown -R 1001:1001 ~/.nanobot/workspace
chmod 711 ~/.nanobot
chmod 700 ~/.nanobot/workspace
```

`entrypoint.setuid.sh` only repairs non-recursive mode bits for root-owned
nanobot state paths. It does not change workspace ownership or permissions.

## Workspace Virtual Environments

The setuid image does not require a separate application venv for nanobot
itself. Exec commands run with `HOME` set to the workspace, so project-local
Python environments live inside the workspace.

On the first `setuid` exec command, nanobot creates `.venv` at the workspace
root if `.venv/bin/python` does not already exist, then prepends `.venv/bin` to
`PATH` before running the requested command. You can also create or manage it
manually:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Because the workspace is owned by the configured exec UID/GID, the lowered exec
process can create and update `.venv` without write access to nanobot's
root-owned config, sessions, or memory paths.

If the lowered UID/GID cannot write the workspace or an existing `.venv`,
nanobot fails the exec command before running user code and prints a repair
hint. For Podman bind mounts, use `podman unshare chown -R <uid>:<gid>` on the
host workspace.

## Run

```bash
podman run --rm \
  --user 0:0 \
  -v ~/.nanobot:/home/nanobot/.nanobot \
  nanobot:setuid agent -m "Hello!"
```

Do not treat this as a rootful Docker sandbox. It is intended for rootless
Podman or equivalent rootless container runtimes.
