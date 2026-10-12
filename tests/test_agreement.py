import pytest

from trajectory_grader.agreement import (
    MIN_N_FOR_KAPPA,
    automated_verdicts,
    cohens_kappa,
    compare,
    missing_reports,
    rule_agreement,
)
from trajectory_grader.grader import grade
from trajectory_grader.labels import GoldLabel
from trajectory_grader.rubric import bad_retry_no_change, redundant_call_after_success
from trajectory_grader.schema import Step, Trajectory

RULES = ["bad_retry_no_change", "redundant_call_after_success"]


def _label(task_id, verdicts):
    return GoldLabel(
        task_id=task_id,
        labeled_by="edgeorgie",
        labeled_at="2026-10-11",
        verdicts=verdicts,
    )


def _traj(task_id, steps):
    return Trajectory(task_id=task_id, agent_name="a", steps=tuple(steps))


# --- Cohen's kappa against hand-computed reference values -----------------
#
# Each expected value below is derived by hand from the definition
# (po - pe) / (1 - pe) rather than from this implementation's own output, so
# the test is an independent oracle and not a snapshot of current behaviour.


def test_kappa_is_one_for_perfect_agreement_with_two_categories_used():
    # po = 1.0; pe = (0.5*0.5) + (0.5*0.5) = 0.5; k = (1-0.5)/(1-0.5) = 1.0
    pairs = [("ok", "ok"), ("violation", "violation")]
    assert cohens_kappa(pairs) == 1.0


def test_kappa_is_zero_when_agreement_is_exactly_chance():
    # 4 items, each rater splits 2/2, agreeing on 2 of 4.
    # po = 0.5; pe = (0.5*0.5)+(0.5*0.5) = 0.5; k = 0.0
    pairs = [
        ("ok", "ok"),
        ("ok", "violation"),
        ("violation", "ok"),
        ("violation", "violation"),
    ]
    assert cohens_kappa(pairs) == 0.0


def test_kappa_is_negative_for_worse_than_chance_agreement():
    # po = 0.0; pe = 0.5; k = (0 - 0.5) / 0.5 = -1.0
    pairs = [("ok", "violation"), ("violation", "ok")]
    assert cohens_kappa(pairs) == -1.0


def test_kappa_matches_the_hand_computed_value_on_a_lopsided_set():
    # 10 items. rater A: 9 ok / 1 violation. rater B: 8 ok / 2 violation.
    # agree on 8 ok + 1 violation = 9  -> po = 0.9
    # pe = (0.9 * 0.8) + (0.1 * 0.2) = 0.72 + 0.02 = 0.74
    # k = (0.9 - 0.74) / (1 - 0.74) = 0.16 / 0.26 = 0.615384...
    pairs = [("ok", "ok")] * 8 + [("ok", "violation")] + [("violation", "violation")]
    assert cohens_kappa(pairs) == pytest.approx(0.16 / 0.26)


def test_kappa_is_undefined_not_perfect_when_only_one_category_is_used():
    """The failure mode this metric exists to catch.

    A rule that never fires agrees perfectly with a gold set where it never
    should have fired — raw agreement 1.0 — while carrying no evidence that
    it can discriminate at all. pe == 1.0 there, so kappa is undefined, and
    reporting it as 1.0 would be the single most flattering lie this
    project could tell.
    """
    pairs = [("ok", "ok")] * 20
    assert cohens_kappa(pairs) is None


def test_kappa_is_undefined_for_an_empty_set():
    assert cohens_kappa([]) is None


# --- rule-level agreement -------------------------------------------------


def test_rule_agreement_counts_and_lists_disagreements():
    stats = rule_agreement(
        "bad_retry_no_change",
        [
            ("t1", "ok", "ok"),
            ("t2", "violation", "ok"),
            ("t3", "violation", "violation"),
        ],
    )
    assert stats.n == 3
    assert stats.agreements == 2
    assert stats.raw_agreement == 2 / 3
    assert stats.disagreements == (("t2", "violation", "ok"),)
    assert "bad_retry_no_change" in stats.describe()


def test_unmeasured_rule_reports_none_not_zero():
    stats = rule_agreement("some_rule", [])
    assert stats.n == 0
    assert stats.raw_agreement is None
    assert stats.kappa is None
    assert "not measured" in stats.describe()


def test_kappa_is_suppressed_below_the_n_floor_not_printed_as_zero():
    """Regression: n=1 with a disagreement printed a hard `0.000`.

    pe = 1*0 + 0*1 = 0, so kappa = (0-0)/(1-0) = 0.0 exactly — which a
    reader takes as "measured, agreement no better than chance" when it is
    a single item. The raw formula is correct; publishing its output at that
    n is not.
    """
    stats = rule_agreement("r", [("t1", "violation", "ok")])
    assert stats.n == 1
    assert stats.raw_agreement == 0.0  # raw agreement IS meaningful, and is kept
    assert stats.kappa is None
    assert "n=1" in stats.kappa_undefined_because
    assert "not reportable" in stats.describe()
    assert "0.000" not in stats.describe().split("kappa")[1]


def test_kappa_is_reported_once_the_floor_is_met():
    # at/above the floor the real value must come through, so the guard is a
    # floor and not a blanket suppression
    pairs = [("t", "ok", "ok")] * 3 + [("t", "violation", "violation")] * 2
    stats = rule_agreement("r", pairs)
    assert stats.n == MIN_N_FOR_KAPPA
    assert stats.kappa == 1.0
    assert stats.kappa_undefined_because == ""
    assert "1.000" in stats.describe()


def test_single_category_above_the_floor_is_still_undefined_with_its_own_reason():
    stats = rule_agreement("r", [("t", "ok", "ok")] * 10)
    assert stats.kappa is None
    assert "single category" in stats.kappa_undefined_because


def test_describe_renders_unreportable_kappa_as_words_not_a_number():
    """Whatever the reason, an absent kappa must never render as a numeral.

    This asserts the *intent* (no decimal value where there is no
    measurement) rather than one specific wording, so tightening the reason
    text cannot break it — but substituting a number still does. At n=2 the
    n-floor is the binding reason; the single-category cause has its own
    test above.
    """
    import re

    stats = rule_agreement("r", [("t1", "ok", "ok"), ("t2", "ok", "ok")])
    assert stats.kappa is None
    rendered = stats.describe()
    kappa_slot = rendered.split("kappa", 1)[1]
    assert not re.search(r"\d\.\d", kappa_slot), (
        f"kappa rendered as a decimal value despite being unmeasured: {rendered}"
    )
    assert stats.kappa_undefined_because
    assert stats.kappa_undefined_because in rendered


# --- automated verdicts ---------------------------------------------------


def test_a_rule_that_did_not_fire_is_an_explicit_ok_verdict():
    # a non-firing rule leaves no trace in the report, but "did not fire" is
    # a real verdict that has to be comparable against a human one
    traj = _traj("t", [Step(kind="tool", tool="x", args={}, ok=True)])
    report = grade(traj, [bad_retry_no_change, redundant_call_after_success])
    assert automated_verdicts(report, RULES) == {
        "bad_retry_no_change": "ok",
        "redundant_call_after_success": "ok",
    }


def test_a_rule_that_fired_is_a_violation_verdict():
    traj = _traj(
        "t",
        [
            Step(kind="tool", tool="x", args={"a": 1}, ok=False),
            Step(kind="tool", tool="x", args={"a": 1}, ok=False),
        ],
    )
    report = grade(traj, [bad_retry_no_change])
    assert automated_verdicts(report, ["bad_retry_no_change"]) == {
        "bad_retry_no_change": "violation"
    }


# --- compare() ------------------------------------------------------------


def test_compare_measures_the_grader_against_human_labels():
    repeated = _traj(
        "t-repeat",
        [
            Step(kind="tool", tool="x", args={"a": 1}, ok=False),
            Step(kind="tool", tool="x", args={"a": 1}, ok=False),
        ],
    )
    clean = _traj("t-clean", [Step(kind="tool", tool="x", args={}, ok=True)])
    graded = {
        t.task_id: grade(t, [bad_retry_no_change, redundant_call_after_success])
        for t in (repeated, clean)
    }
    gold = [
        _label("t-repeat", {"bad_retry_no_change": "violation"}),
        _label("t-clean", {"bad_retry_no_change": "ok"}),
    ]
    stats = {s.rule: s for s in compare(graded, gold, RULES)}
    assert stats["bad_retry_no_change"].n == 2
    assert stats["bad_retry_no_change"].agreements == 2
    # the second rule was never labeled by a human -> not measured, not 1.0
    assert stats["redundant_call_after_success"].n == 0
    assert stats["redundant_call_after_success"].raw_agreement is None


def test_compare_ignores_unclear_human_verdicts():
    clean = _traj("t", [Step(kind="tool", tool="x", args={}, ok=True)])
    graded = {"t": grade(clean, [bad_retry_no_change])}
    gold = [_label("t", {"bad_retry_no_change": "unclear"})]
    stats = {s.rule: s for s in compare(graded, gold, RULES)}
    # an undecided human label is not a disagreement
    assert stats["bad_retry_no_change"].n == 0


def test_compare_skips_rules_the_gold_set_names_but_the_rubric_does_not():
    clean = _traj("t", [Step(kind="tool", tool="x", args={}, ok=True)])
    graded = {"t": grade(clean, [bad_retry_no_change])}
    gold = [_label("t", {"a_rule_that_does_not_exist": "ok"})]
    stats = {s.rule: s for s in compare(graded, gold, RULES)}
    assert all(s.n == 0 for s in stats.values())


def test_missing_reports_surfaces_labeled_but_ungraded_trajectories():
    # a silently shrinking denominator is how a published number drifts
    # away from the gold set it claims to describe
    gold = [_label("labeled-but-missing", {"bad_retry_no_change": "ok"})]
    assert missing_reports({}, gold) == ["labeled-but-missing"]
    assert compare({}, gold, RULES)[0].n == 0
