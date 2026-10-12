import json
from pathlib import Path

import pytest

from trajectory_grader.adapters.triage_desk import (
    _coalesce_tool_steps,
    trajectory_from_triage_desk_log,
)
from trajectory_grader.cli import DEFAULT_RULES
from trajectory_grader.grader import grade
from trajectory_grader.rubric import redundant_call_after_success

EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "subject-under-test"
    / "triage-desk-run-issue24.json"
)


def test_adapter_converts_real_triage_desk_log_shape():
    entry = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    traj = trajectory_from_triage_desk_log(entry)
    assert traj.task_id == "triage-desk-issue-24"
    assert traj.agent_name == "edgeorgie/triage-desk"
    assert traj.final_action == "bug"
    # ONE call, not two: the raw log records this call twice (pre- and
    # post-execution, same id) because of how triage-desk's agent loop
    # emits onStep. See the adapter's module docstring.
    tool_names = [s.tool for s in traj.tool_steps()]
    assert tool_names == ["submit_triage"]


def test_the_raw_log_really_does_contain_the_duplicate_this_adapter_coalesces():
    """Pins the upstream quirk this coalescing exists for.

    If triage-desk ever stops double-logging, this test fails and tells the
    next reader the normalisation may no longer be needed — rather than the
    coalescing silently becoming dead code nobody can justify.
    """
    entry = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw_tools = [s for s in entry["steps"] if s["kind"] == "tool"]
    assert len(raw_tools) == 2
    assert raw_tools[0]["id"] == raw_tools[1]["id"]
    # only the post-execution record carries the outcome
    assert "output" not in raw_tools[0]
    assert raw_tools[1]["output"] == "Triage recorded."


def test_the_real_run_is_clean_under_the_default_rubric():
    """The corrected result for this real trajectory.

    Before the adapter coalesced the double-logged pair, this run tripped
    `redundant_call_after_success` — a false positive that would have fired
    on *every* single-call triage-desk run, since the duplication came from
    the logger rather than from any decision the agent made. Asserting the
    clean result keeps that regression from returning.
    """
    entry = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    report = grade(trajectory_from_triage_desk_log(entry), DEFAULT_RULES)
    assert report.passed, report.summary()
    assert report.num_tool_calls == 1


def test_a_genuine_repeat_call_is_still_caught():
    # the quirk-fix must not blunt the rule: a real second call gets a
    # fresh id from the model, so it must still be flagged
    entry = {
        "issue": 1,
        "result": {"kind": "bug"},
        "steps": [
            {"kind": "tool", "id": "call-1", "name": "t", "input": {"a": 1}, "output": "ok"},
            {"kind": "tool", "id": "call-2", "name": "t", "input": {"a": 1}, "output": "ok"},
        ],
    }
    report = grade(trajectory_from_triage_desk_log(entry), [redundant_call_after_success])
    assert not report.passed
    assert report.violations[0].rule == "redundant_call_after_success"


def test_a_same_id_pair_naming_two_different_tools_is_not_merged():
    """Regression: blind id-keyed merging DELETED a real tool call.

    An id-only merge collapsed `get_issue` then `submit_triage` (same id,
    both with output) into a single `submit_triage` step — the `get_issue`
    call vanished with no warning, destroying exactly the signal
    `wrong_tool_before_right` exists to detect.

    triage-desk ids genuinely repeat across distinct calls:
    `scripts/triage-bot.ts` hardcodes `id: "heuristic-1"` for every
    heuristic run, and `lib/agent.ts` falls back to `id: b.id ?? ""`.
    """
    entry = {
        "issue": 1,
        "result": {"kind": "bug"},
        "steps": [
            {"kind": "tool", "id": "same", "name": "get_issue", "input": {"n": 1}, "output": "ok"},
            {
                "kind": "tool",
                "id": "same",
                "name": "submit_triage",
                "input": {"k": "bug"},
                "output": "ok",
            },
        ],
    }
    traj = trajectory_from_triage_desk_log(entry)
    assert [s.tool for s in traj.tool_steps()] == ["get_issue", "submit_triage"]


def test_a_genuine_repeat_reusing_an_id_is_still_caught():
    """Regression: a real duplicate that reused an id was silently collapsed.

    Both records carry an outcome, which is what distinguishes a genuine
    immediate repeat from the pre/post logging pair. Under id-only merging
    this reported a clean trajectory.
    """
    entry = {
        "issue": 1,
        "result": {"kind": "bug"},
        "steps": [
            {
                "kind": "tool",
                "id": "h1",
                "name": "submit_triage",
                "input": {"a": 1},
                "output": "ok",
            },
            {
                "kind": "tool",
                "id": "h1",
                "name": "submit_triage",
                "input": {"a": 1},
                "output": "ok",
            },
        ],
    }
    report = grade(trajectory_from_triage_desk_log(entry), [redundant_call_after_success])
    assert not report.passed
    assert report.violations[0].rule == "redundant_call_after_success"


def test_a_retry_reusing_an_id_is_still_caught():
    entry = {
        "issue": 1,
        "result": {},
        "steps": [
            {
                "kind": "tool",
                "id": "h1",
                "name": "t",
                "input": {"a": 1},
                "output": "boom",
                "isError": True,
            },
            {
                "kind": "tool",
                "id": "h1",
                "name": "t",
                "input": {"a": 1},
                "output": "boom",
                "isError": True,
            },
        ],
    }
    from trajectory_grader.rubric import bad_retry_no_change

    report = grade(trajectory_from_triage_desk_log(entry), [bad_retry_no_change])
    assert not report.passed
    assert report.violations[0].rule == "bad_retry_no_change"


def test_an_empty_string_id_pair_is_still_coalesced():
    """Regression: the empty-id path reopened the original false positive.

    `lib/agent.ts` emits `id: b.id ?? ""` when a model omits an id. A
    truthiness check (`raw.get("id")`) skips coalescing for `""`, so the
    double-logged pair survived as two steps and
    `redundant_call_after_success` fired again — reproducing the exact bug
    the coalescing exists to fix. Presence of the key, not its truthiness,
    is the correct test.
    """
    entry = {
        "issue": 1,
        "result": {"kind": "bug"},
        "steps": [
            {"kind": "tool", "id": "", "name": "submit_triage", "input": {"a": 1}},
            {"kind": "tool", "id": "", "name": "submit_triage", "input": {"a": 1}, "output": "ok"},
        ],
    }
    traj = trajectory_from_triage_desk_log(entry)
    assert len(traj.tool_steps()) == 1
    assert grade(traj, [redundant_call_after_success]).passed


def test_three_consecutive_same_id_steps_do_not_all_collapse():
    # a pre/post pair is exactly two records; a third same-id step with its
    # own outcome is another action and must survive
    entry = {
        "issue": 1,
        "result": {},
        "steps": [
            {"kind": "tool", "id": "x", "name": "t", "input": {}},
            {"kind": "tool", "id": "x", "name": "t", "input": {}, "output": "ok"},
            {"kind": "tool", "id": "x", "name": "t", "input": {}, "output": "ok"},
        ],
    }
    assert len(trajectory_from_triage_desk_log(entry).tool_steps()) == 2


def test_coalesce_keeps_the_post_execution_outcome():
    steps = [
        {"kind": "tool", "id": "x", "name": "t", "input": {}},
        {"kind": "tool", "id": "x", "name": "t", "input": {}, "output": "done", "isError": False},
    ]
    merged = _coalesce_tool_steps(steps)
    assert len(merged) == 1
    assert merged[0]["output"] == "done"


def test_coalesce_leaves_thoughts_and_idless_steps_alone():
    steps = [
        {"kind": "thought", "text": "a"},
        {"kind": "thought", "text": "b"},
        {"kind": "tool", "name": "t", "input": {}},
        {"kind": "tool", "name": "t", "input": {}},
    ]
    assert len(_coalesce_tool_steps(steps)) == 4


def test_coalesce_does_not_merge_across_an_intervening_step():
    # two calls with the same id separated by a thought are not the
    # pre/post pair this handles; don't guess at merging them
    steps = [
        {"kind": "tool", "id": "x", "name": "t", "input": {}},
        {"kind": "thought", "text": "hmm"},
        {"kind": "tool", "id": "x", "name": "t", "input": {}},
    ]
    assert len(_coalesce_tool_steps(steps)) == 3


def test_an_errored_tool_step_is_not_ok():
    entry = {
        "issue": 2,
        "result": {},
        "steps": [
            {"kind": "tool", "id": "c", "name": "t", "input": {}, "output": "boom", "isError": True}
        ],
    }
    traj = trajectory_from_triage_desk_log(entry)
    assert traj.tool_steps()[0].ok is False


def test_unknown_step_kind_is_rejected_rather_than_skipped():
    with pytest.raises(ValueError, match="unknown triage-desk step kind"):
        trajectory_from_triage_desk_log(
            {"issue": 3, "result": {}, "steps": [{"kind": "telepathy"}]}
        )
