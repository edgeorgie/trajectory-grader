import json

import pytest

from trajectory_grader.labels import (
    GoldLabel,
    gold_label_from_dict,
    load_gold_label,
    load_gold_set,
)


def _valid(**over):
    base = {
        "task_id": "t1",
        "labeled_by": "edgeorgie",
        "labeled_at": "2026-10-11",
        "verdicts": {"bad_retry_no_change": "ok"},
    }
    base.update(over)
    return base


def test_round_trips_a_valid_label():
    label = gold_label_from_dict(_valid(notes="because the retry changed args"))
    assert label.task_id == "t1"
    assert label.labeled_by == "edgeorgie"
    assert label.verdicts == {"bad_retry_no_change": "ok"}
    assert label.notes == "because the retry changed args"


@pytest.mark.parametrize("field", ["labeled_by", "labeled_at"])
def test_provenance_is_required(field):
    # an unauditable gold label is worth less than no gold label
    with pytest.raises(ValueError, match=field):
        gold_label_from_dict(_valid(**{field: ""}))


def test_rejects_an_unknown_verdict():
    with pytest.raises(ValueError, match="must be one of"):
        gold_label_from_dict(_valid(verdicts={"bad_retry_no_change": "probably fine"}))


def test_rejects_a_label_with_no_verdicts():
    with pytest.raises(ValueError, match="records nothing"):
        gold_label_from_dict(_valid(verdicts={}))


def test_rejects_non_object_verdicts():
    with pytest.raises(ValueError, match="rule -> verdict"):
        gold_label_from_dict(_valid(verdicts=["ok"]))


def test_missing_required_key_raises_rather_than_defaulting():
    bad = _valid()
    del bad["labeled_by"]
    with pytest.raises(KeyError):
        gold_label_from_dict(bad)


def test_scorable_drops_unclear_but_keeps_the_rest():
    label = GoldLabel(
        task_id="t",
        labeled_by="e",
        labeled_at="2026-10-11",
        verdicts={"a": "ok", "b": "unclear", "c": "violation"},
    )
    assert label.scorable() == {"a": "ok", "c": "violation"}
    # the raw record keeps `unclear` — it is evidence of a judgement call,
    # not noise to be discarded at write time
    assert label.verdicts["b"] == "unclear"


def test_load_gold_set_is_empty_for_an_unlabeled_directory(tmp_path):
    # the honest answer while the gold set is still being built
    assert load_gold_set(tmp_path) == []


def test_load_gold_set_reads_sorted_and_round_trips(tmp_path):
    for task in ("t2", "t1"):
        (tmp_path / f"{task}.json").write_text(json.dumps(_valid(task_id=task)), encoding="utf-8")
    labels = load_gold_set(tmp_path)
    assert [label.task_id for label in labels] == ["t1", "t2"]


def test_load_gold_set_rejects_duplicate_task_ids(tmp_path):
    # two labels for one trajectory would be counted twice in agreement
    (tmp_path / "a.json").write_text(json.dumps(_valid(task_id="dup")), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(_valid(task_id="dup")), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate task_id"):
        load_gold_set(tmp_path)


def test_load_gold_label_reads_a_single_file(tmp_path):
    path = tmp_path / "one.json"
    path.write_text(json.dumps(_valid(task_id="solo")), encoding="utf-8")
    assert load_gold_label(path).task_id == "solo"


def test_the_committed_gold_set_directory_is_loadable():
    """The real gold-set dir must always parse, and must not be empty.

    This is the guard that matters as labels get added by hand: a typo in a
    hand-written JSON label should fail CI here, not silently skew a
    published agreement number.

    The `>= 1` assertion is load-bearing, not decoration. Without it this
    test passes on an EMPTY gold set — `load_gold_set` returns `[]`,
    `isinstance([], list)` holds, and the per-label loop never runs — so
    deleting every label would leave it green while claiming to guard them.
    """
    from pathlib import Path

    gold_dir = Path(__file__).resolve().parent.parent / "gold-set"
    labels = load_gold_set(gold_dir)
    assert len(labels) >= 1, f"the committed gold set is empty: {gold_dir}"
    for label in labels:
        assert label.labeled_by, f"{label.task_id} has no attributable labeler"
        assert label.labeled_at, f"{label.task_id} has no label date"
        assert label.verdicts, f"{label.task_id} records no verdicts"


def test_the_committed_labels_name_only_real_rubric_rules():
    """A label naming a rule that does not exist is silently unmeasurable.

    `compare()` skips verdicts for unknown rule names, so a typo in a rule
    name inside a hand-written label removes it from the denominator with no
    error anywhere. Catch it here instead.
    """
    from pathlib import Path

    import trajectory_grader.rubric as rubric

    gold_dir = Path(__file__).resolve().parent.parent / "gold-set"
    for label in load_gold_set(gold_dir):
        for rule in label.verdicts:
            assert hasattr(rubric, rule), (
                f"{label.task_id} labels rule {rule!r}, which does not exist in "
                "rubric.py — this verdict would be silently ignored"
            )
