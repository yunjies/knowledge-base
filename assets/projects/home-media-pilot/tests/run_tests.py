"""Run the mirrored suite and write a machine-readable result artifact.

Usage:
    python3 tests/run_tests.py [--pytest-args "..."] [--report PATH]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent

# Every file this suite writes lands under one ignored directory, so a run
# never leaves anything for a reviewer to mistake for source. The directory is
# deliberately outside `.pytest_cache/` (pytest owns that) and inside the tree
# (unlike the system temporary directory, which a reboot discards): the report
# exists to make one run reproducible later, so it must survive the run.
ARTIFACTS_DIR = TESTS_ROOT / ".artifacts"
DEFAULT_REPORT = ARTIFACTS_DIR / "report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-args", default="")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    command = [sys.executable, "-m", "pytest", "-q", str(TESTS_ROOT)]
    if args.pytest_args:
        command.extend(args.pytest_args.split())

    started_at = datetime.now(UTC)
    completed = subprocess.run(command, capture_output=True, text=True)
    finished_at = datetime.now(UTC)

    report = {
        "command": command,
        "exit_code": completed.returncode,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
