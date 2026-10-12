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
    """The derived list must be exactly the rubric's rule names.

    `_rule_names()` exists so the calibration report cannot silently drift
    from the rubric when a rule is added — a hand-maintained list would
    under-report the rubric's real size and quietly shrink the number of
    rules being calibrated.

    The expected set is written out literally here on purpose. Asserting
    only `len(names) == len(DEFAULT_RULES)` would be tautological (the
    derivation iterates DEFAULT_RULES, so the length matches by
    construction) and would not catch a rule being renamed.
    """
    assert set(_rule_names()) == {
        "wrong_tool_before_right",
        "bad_retry_no_change",
        "redundant_call_after_success",
        "no_terminal_action",
    }
    names = _rule_names()
    assert len(names) == len(DEFAULT_RULES)
    assert len(set(names)) == len(names), f"duplicate derived rule names: {names}"

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
    # kappa must never be a number at n=1, where the formula yields a
    # confident-looking 0.000/1.000 from a single item
    assert "not reportable" in out
    assert "n=1" in out


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
    """Shape detection, proven by a canonical file actually being measured.

    The loader detects shape, not filename: canonical files use `tool`/`args`
    where a raw triage-desk log uses `name`/`input`. Asserting only that the
    run exits 0 would not prove the canonical file was *understood* — so a
    matching gold label is written here, making the canonical trajectory the
    thing the agreement number is computed from.
    """
    canonical = {
        "task_id": "canon-1",
        "agent_name": "a",
        "steps": [{"kind": "tool", "tool": "submit_triage", "args": {}, "ok": True}],
    }
    traj_dir = tmp_path / "trajectories"
    traj_dir.mkdir()
    (traj_dir / "c.json").write_text(json.dumps(canonical), encoding="utf-8")

    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()
    (gold_dir / "canon-1.json").write_text(
        json.dumps(
            {
                "task_id": "canon-1",
                "labeled_by": "test",
                "labeled_at": "2026-10-12",
                "verdicts": {"no_terminal_action": "ok"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["calibrate", str(gold_dir), str(traj_dir)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "gold labels: 1   graded trajectories: 1" in out
    # the canonical file was parsed AND scored: a shape the loader failed to
    # understand would leave this rule at n=0 and trip the nothing-measurable
    # exit below instead
    assert "no_terminal_action: raw agreement 1.000 (1/1)" in out


def test_calibrate_fails_when_every_label_is_orphaned(tmp_path, capsys):
    """Nothing compared must not exit 0, even with a valid gold set.

    Every label loads cleanly here, but no graded run matches any label's
    task_id, so no rule has a single scorable pair. Exiting 0 would let CI
    stay green while the published agreement number silently lost its basis
    — the same failure as an empty gold set, so it gets the same exit code.
    """
    canonical = {
        "task_id": "unmatched-1",
        "agent_name": "a",
        "steps": [{"kind": "tool", "tool": "submit_triage", "args": {}, "ok": True}],
    }
    (tmp_path / "c.json").write_text(json.dumps(canonical), encoding="utf-8")
    rc = main(["calibrate", str(GOLD), str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 2
    # the orphaned label must stay visible rather than vanishing from the
    # denominator unannounced
    assert "labeled but not graded" in out
    assert "Nothing was measurable" in out


def test_calibrate_help_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "trajectory_grader.calibrate", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert proc.returncode == 0
    assert "agreement" in proc.stdout.lower()
