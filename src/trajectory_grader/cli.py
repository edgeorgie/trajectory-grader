"""Tiny CLI: grade a canonical-schema trajectory JSON file against the
default rubric and print the report.

This intentionally hardcodes a small, sensible default rubric for the
triage-desk-shaped example rather than accepting arbitrary rubric config —
configurable rubric files are future work (see ROADMAP.md).

Exit codes are part of the contract, so this is usable as a CI gate on a
recorded trajectory:

    0  the trajectory passed every rule in the default rubric
    1  at least one rule fired (the report lists which, and at which step)
    2  usage error / unreadable or malformed trajectory file
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

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

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_USAGE = 2


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Factored out so tests can assert on the CLI surface (and on ``--help``
    not crashing) without going through ``main``.
    """
    parser = argparse.ArgumentParser(
        prog="python -m trajectory_grader.cli",
        description=(
            "Grade a canonical-schema agent trajectory against the default process-quality rubric."
        ),
        epilog=(
            "Exit status: 0 = no violations, 1 = at least one rule fired, 2 = usage or input error."
        ),
    )
    parser.add_argument(
        "trajectory",
        metavar="TRAJECTORY.json",
        help=(
            "Path to a trajectory JSON file in the canonical schema "
            "(see src/trajectory_grader/schema.py). Raw triage-desk logs "
            "must be converted first — see adapters/triage_desk.py."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    ``argv`` follows the ``sys.argv`` convention (element 0 is the program
    name) so that ``main(sys.argv)`` works; pass ``None`` to read
    ``sys.argv`` directly.
    """
    args = list(sys.argv if argv is None else argv)[1:]
    try:
        ns = _build_parser().parse_args(args)
    except SystemExit as exc:  # argparse exits 0 on --help, 2 on bad usage
        return int(exc.code or EXIT_OK)

    try:
        with open(ns.trajectory, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        print(f"error: cannot read {ns.trajectory!r}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except json.JSONDecodeError as exc:
        print(f"error: {ns.trajectory!r} is not valid JSON: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        traj = trajectory_from_dict(data)
    except (TypeError, ValueError, KeyError) as exc:
        print(
            f"error: {ns.trajectory!r} is not a valid canonical trajectory: {exc}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    report = grade(traj, DEFAULT_RULES)
    print(report.summary())
    return EXIT_OK if report.passed else EXIT_VIOLATIONS


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
