#!/usr/bin/env python3
"""Convert a raw triage-desk run log to canonical schema on stdout.

Exists so CI can exercise the adapter -> canonical-schema -> CLI path over
the committed REAL example log, rather than only over synthetic unit-test
fixtures. Keeping it as a committed script (instead of an inline heredoc in
the workflow) means the exact command CI runs can also be run locally.

Usage:
    python scripts/to_canonical.py examples/subject-under-test/<log>.json > canonical.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from trajectory_grader.adapters.triage_desk import trajectory_from_triage_desk_log


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <triage-desk-log.json>", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        raw = json.load(f)
    traj = trajectory_from_triage_desk_log(raw)
    payload = asdict(traj)
    payload["steps"] = list(payload["steps"])
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
