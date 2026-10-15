#!/usr/bin/env bash
# Install the repository's local git hooks (currently commit-msg) into this clone's hooks folder.
# Copies rather than setting core.hooksPath, so hooks from other tools (such as Git LFS) keep working.
# Run from anywhere in the clone:  bash scripts/install_git_hooks.sh
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
hooks="$(git rev-parse --git-path hooks)"
mkdir -p "$hooks"
cp "$root/scripts/git-hooks/commit-msg" "$hooks/commit-msg"
chmod +x "$hooks/commit-msg"
echo "Installed commit-msg hook in $hooks"
