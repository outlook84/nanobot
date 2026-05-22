#!/bin/sh
dir="$HOME/.nanobot"

if [ "$(id -u)" != "0" ]; then
    cat >&2 <<EOF
Error: setuid sandbox image must run as container UID 0.

Use a rootless container runtime and pass:
  podman run --user 0:0 ...
EOF
    exit 1
fi

# Repair only mode bits. Bind-mount ownership should be prepared from the host
# with `podman unshare chown -R <uid>:<gid> ~/.nanobot/workspace`.
[ -d "$HOME" ] && chmod 711 "$HOME" 2>/dev/null || true
[ -d "$dir" ] && chmod 711 "$dir" 2>/dev/null || true
[ -f "$dir/config.json" ] && chmod 600 "$dir/config.json" 2>/dev/null || true
[ -d "$dir/sessions" ] && chmod 700 "$dir/sessions" 2>/dev/null || true
[ -d "$dir/memory" ] && chmod 700 "$dir/memory" 2>/dev/null || true

exec nanobot "$@"
