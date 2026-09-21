#!/usr/bin/env bash
# Run the documentation guard. The uv cache lives in the repository because the
# host's default cache directory is read-only; the pytest version is pinned in
# the command rather than in a pyproject.toml, so this directory stays the only
# thing the guard adds to the repository.
set -euo pipefail
cd "$(dirname "$0")/.."
UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest _lint -q "$@"
