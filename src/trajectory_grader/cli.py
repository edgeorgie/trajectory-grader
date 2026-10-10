"""Tiny CLI: grade a canonical-schema trajectory JSON file against the
default rubric and print the report.

This intentionally hardcodes a small, sensible default rubric for the
triage-desk-shaped example rather than accepting arbitrary rubric config —
configurable rubric files are future work (see ROADMAP.md).
"""

from __future__ import annotations

import json
import sys

from .grader import grade
from .rubric import (
    bad_retry_no_change,
    no_terminal_action,
    redundant_call_after_success,
    wrong_tool_before_right,
)
from .schema import trajectory_from_dict

DEFAULT_RULES = [
    wrong_tool_before_right(wrong_tool="get_issue", right_tool="find_similar"),
    bad_retry_no_change,
    redundant_call_after_success,
    no_terminal_action(terminal_tools=frozenset({"submit_triage"})),
]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m trajectory_grader.cli <trajectory.json>", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        data = json.load(f)
    traj = trajectory_from_dict(data)
    report = grade(traj, DEFAULT_RULES)
    print(report.summary())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
