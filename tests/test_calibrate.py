import json
import subprocess
import sys
from pathlib import Path

from trajectory_grader.calibrate import _rule_names, main
from trajectory_grader.cli import DEFAULT_RULES

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples" / "subject-under-test"
GOLD = REPO / "gold-set"


def test_rule_names_are_derived_from_the_rubric_not_restated():
    """The derived list must cover every rule in DEFAULT_RULES, exactly.

    `_rule_names()` exists so the calibration report cannot silently drift
    from the rubric when a rule is added — a hand-maintained list would
    under-report the rubric's real size and quietly shrink the number of
    rules being calibrated. This asserts the derivation against the rubric
    itself, so adding a rule with no calibration coverage fails here.
    """
    names = _rule_names()
    assert len(names) == len(DEFAULT_RULES)
    assert len(set(names)) == len(names), f"duplicate derived rule names: {names}"
    # every derived name must be a real attribute of the rubric module
    import trajectory_grader.rubric as rubric

    for name in names:
        assert hasattr(rubric, name), (
            f"derived rule name {name!r} does not exist in rubric.py — the "
            "derivation is wrong, or a rule was renamed without updating it"
        )


def test_derived_names_match_the_violations_the_rules_actually_emit():
    """Guards the factory-closure case.

    A rule built by a factory has `__qualname__` like
    `wrong_tool_before_right.<locals>.check`, so a naive `__name__` read
    would call it "check" and never match the `rule` field on the
    Violations it emits — making its agreement silently unmeasurable.
    """
    from trajectory_grader.rubric import Violation
    from trajectory_grader.schema import Step, Trajectory

    # a trajectory engineered to trip every rule in the default rubric
    traj = Trajectory(
        task_id="t",
        agent_name="a",
        steps=(
            Step(kind="tool", tool="get_issue", args={}, ok=False),
            Step(kind="tool", tool="get_issue", args={}, ok=False),
            Step(kind="tool", tool="find_similar", args={}, ok=True),
            Step(kind="tool", tool="find_similar", args={}, ok=True),
        ),
    )
    emitted: set[str] = set()
    for rule in DEFAULT_RULES:
        for v in rule(traj):
            assert isinstance(v, Violation)
            emitted.add(v.rule)
    # every rule name that fired must be one the calibration layer knows
    assert emitted, "the fixture failed to trip any rule; it no longer guards anything"
    assert emitted <= set(_rule_names()), (
        f"rules emitted {sorted(emitted - set(_rule_names()))} which the "
        "calibration layer does not know about"
    )


def test_calibrate_reports_against_the_committed_gold_set(capsys):
    rc = main(["calibrate", str(GOLD), str(EXAMPLES)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "gold labels: 1" in out
    assert "per-rule agreement:" in out
    # kappa must be rendered as undefined at n=1, never as a flattering 1.000
    assert "undefined" in out


def test_calibrate_refuses_an_empty_gold_set(tmp_path, capsys):
    rc = main(["calibrate", str(tmp_path), str(EXAMPLES)])
    out = capsys.readouterr().out
    assert rc == 2
    assert "No gold labels yet" in out


def test_calibrate_rejects_a_non_directory(tmp_path, capsys):
    rc = main(["calibrate", str(tmp_path / "nope"), str(EXAMPLES)])
    assert rc == 2
    assert "is not a directory" in capsys.readouterr().err


def test_calibrate_fails_loudly_on_a_malformed_label(tmp_path, capsys):
    (tmp_path / "bad.json").write_text('{"task_id": "x"}', encoding="utf-8")
    rc = main(["calibrate", str(tmp_path), str(EXAMPLES)])
    assert rc == 2
    assert "cannot load gold set" in capsys.readouterr().err


def test_calibrate_accepts_canonical_schema_files_too(tmp_path, capsys):
    # the loader detects shape, not filename: canonical files use tool/args
    canonical = {
        "task_id": "canon-1",
        "agent_name": "a",
        "steps": [{"kind": "tool", "tool": "submit_triage", "args": {}, "ok": True}],
    }
    (tmp_path / "c.json").write_text(json.dumps(canonical), encoding="utf-8")
    rc = main(["calibrate", str(GOLD), str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    # the gold label's task_id has no matching graded run here, so it must be
    # surfaced as orphaned rather than vanishing from the denominator
    assert "labeled but not graded" in out


def test_calibrate_help_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "trajectory_grader.calibrate", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert proc.returncode == 0
    assert "agreement" in proc.stdout.lower()
