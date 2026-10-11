"""Report rubric-vs-human agreement over the gold set.

Separate entrypoint from ``cli.py`` on purpose: grading one trajectory and
measuring the grader against human judgement are different jobs with
different inputs, and collapsing them into one command with mode flags
makes both harder to read.

    python -m trajectory_grader.calibrate gold-set/ examples/subject-under-test/

Exit codes:

    0  a report was produced (even if agreement is poor — a bad number that
       is honestly reported is a successful run of this tool)
    2  usage error, or nothing could be measured at all
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .adapters.triage_desk import trajectory_from_triage_desk_log
from .agreement import compare, missing_reports
from .cli import DEFAULT_RULES
from .grader import grade
from .labels import load_gold_set
from .schema import Trajectory, trajectory_from_dict

EXIT_OK = 0
EXIT_USAGE = 2

#: Rule names in the default rubric, in the order the rubric applies them.
#: Hand-maintaining this list would let it drift from DEFAULT_RULES the
#: first time a rule is added, so it is derived at runtime instead — see
#: ``_rule_names``.


def _rule_names() -> list[str]:
    """Rule names for the default rubric, derived from the rubric itself.

    Each rule is either a plain function (``__name__`` is the rule name) or
    a closure returned by a factory, in which case the name is recovered
    from the factory's qualified name. Deriving rather than restating keeps
    this in step with ``DEFAULT_RULES`` automatically.
    """
    names = []
    for rule in DEFAULT_RULES:
        qualname = getattr(rule, "__qualname__", rule.__name__)
        # a factory-built rule has qualname like "wrong_tool_before_right.<locals>.check"
        names.append(qualname.split(".<locals>.")[0] if ".<locals>." in qualname else rule.__name__)
    return names


def _load_trajectory(path: Path) -> Trajectory:
    """Load a trajectory, accepting either canonical or raw triage-desk shape.

    Detected by structure rather than filename: a raw triage-desk log has
    tool steps keyed ``name``/``input``, the canonical schema uses
    ``tool``/``args``.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    tool_steps = [s for s in data.get("steps", []) if s.get("kind") == "tool"]
    if tool_steps and "name" in tool_steps[0] and "tool" not in tool_steps[0]:
        return trajectory_from_triage_desk_log(data)
    return trajectory_from_dict(data)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m trajectory_grader.calibrate",
        description=(
            "Report agreement between the default rubric and the hand-labeled gold set, "
            "per rule, as raw agreement and Cohen's kappa."
        ),
        epilog="Exit status: 0 = a report was produced, 2 = usage error or nothing measurable.",
    )
    parser.add_argument(
        "gold_dir",
        metavar="GOLD_SET_DIR",
        help="Directory of hand-written gold-label JSON files (one per trajectory).",
    )
    parser.add_argument(
        "trajectory_dir",
        metavar="TRAJECTORY_DIR",
        help=(
            "Directory of trajectory JSON files to grade. Canonical-schema or raw "
            "triage-desk logs are both accepted (detected by structure)."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)[1:]
    try:
        ns = _build_parser().parse_args(args)
    except SystemExit as exc:
        return int(exc.code or EXIT_OK)

    gold_dir, traj_dir = Path(ns.gold_dir), Path(ns.trajectory_dir)
    for d in (gold_dir, traj_dir):
        if not d.is_dir():
            print(f"error: {str(d)!r} is not a directory", file=sys.stderr)
            return EXIT_USAGE

    try:
        gold = load_gold_set(gold_dir)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: cannot load gold set {str(gold_dir)!r}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    rules = _rule_names()
    graded = {}
    for path in sorted(traj_dir.glob("*.json")):
        try:
            traj = _load_trajectory(path)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"warning: skipping {path.name}: {exc}", file=sys.stderr)
            continue
        graded[traj.task_id] = grade(traj, DEFAULT_RULES)

    print(f"gold labels: {len(gold)}   graded trajectories: {len(graded)}")

    if not gold:
        print(
            "\nNo gold labels yet, so no agreement can be reported. This is the honest\n"
            "state until trajectories are labeled by hand — see gold-set/README.md.\n"
            "Do not publish a calibration number sourced from an empty gold set."
        )
        return EXIT_USAGE

    orphans = missing_reports(graded, gold)
    if orphans:
        print(f"\nlabeled but not graded (excluded from every denominator): {orphans}")

    print("\nper-rule agreement:")
    for stats in compare(graded, gold, rules):
        print(f"  {stats.describe()}")
        for task, auto, human in stats.disagreements:
            print(f"      disagreement on {task}: rubric said {auto}, human said {human}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
