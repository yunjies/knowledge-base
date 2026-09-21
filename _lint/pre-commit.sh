#!/usr/bin/env bash
# Run the documentation guard before a commit that touches a document.
#
# This is the local half of the guard; `.github/workflows/guard.yml` is the half
# that runs where nobody can skip it. A hook can always be bypassed, so it is
# not the enforcement — it is the fast feedback that keeps a broken document
# from reaching the push in the first place.
#
# Install with `bash _lint/install-hook.sh`.
set -euo pipefail

root="$(git rev-parse --show-toplevel)"

# Only documents and the guard itself are worth a run. A commit that changes
# nothing else cannot have broken a document rule, and running the guard anyway
# would train the author to reach for `--no-verify`.
changed="$(git diff --cached --name-only --diff-filter=ACMR)"
if ! grep -qE '^(AGENTS\.md|_lint/|_meta/|assets/.*\.md$)' <<<"$changed"; then
  exit 0
fi

echo "documentation guard: a document changed, running _lint"
if ! "$root/_lint/run.sh"; then
  cat >&2 <<'MSG'

The documentation guard failed. Fix the document — or, if the guard misreads it,
fix the guard. Do not loosen a check to make it pass: a green earned by weakening
an assertion is a FAIL, not a PASS.
MSG
  exit 1
fi
