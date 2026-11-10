#!/bin/sh
# Install the versioned git hooks into .git/hooks.
set -eu

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
HOOKS_SRC="$ROOT/scripts/hooks"
HOOKS_DST="$ROOT/.git/hooks"

mkdir -p "$HOOKS_DST"

for hook in "$HOOKS_SRC"/*; do
  [ -f "$hook" ] || continue
  name="$(basename "$hook")"
  cp "$hook" "$HOOKS_DST/$name"
  chmod +x "$HOOKS_DST/$name"
  echo "Installed hook: $name"
done
