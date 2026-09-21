#!/usr/bin/env bash
# Point git at this directory's hooks, so the guard runs before a commit.
#
# `core.hooksPath` is used rather than copying a file into `.git/hooks/`: that
# directory is not version-controlled, so a hook placed there would exist on the
# machine that installed it and nowhere else, and a clone would silently have no
# guard at all.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

git config core.hooksPath _lint/hooks
mkdir -p _lint/hooks
ln -sf ../pre-commit.sh _lint/hooks/pre-commit
chmod +x _lint/pre-commit.sh _lint/hooks/pre-commit

echo "installed: core.hooksPath = _lint/hooks"
echo "the guard now runs before a commit that touches a document"
echo "to remove it: git config --unset core.hooksPath"
