"""Tests for the budget-keeper governor-event adapter.

The committed `.jsonl` files under
`examples/subject-under-test/budget-keeper/` are REAL captured runs of
`budget-keeper --json` (see that directory's README for the exact commands),
so these tests assert against output the governor actually produced rather
than a fixture written to match the adapter.
"""

from pathlib import Path

import pytest

from trajectory_grader.adapters.budget_keeper import (
    TERMINAL_STEP_NAME,
    load_governor_jsonl,
    trajectory_from_governor_events,
)
from trajectory_grader.grader import grade
from trajectory_grader.rubric import no_terminal_action, redundant_call_after_success

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "subject-under-test" / "budget-keeper"

COMPLETED = EXAMPLES / "completed-express-budget-0.50.jsonl"
HALTED_AFTER_1 = EXAMPLES / "halted-after-1-of-20-nextjs-budget-0.02.jsonl"
HALTED_AFTER_2 = EXAMPLES / "halted-after-2-of-20-nextjs-budget-0.60.jsonl"
REFUSED_AT_0 = EXAMPLES / "refused-at-step-0-express-budget-0.0008.jsonl"


# --- the committed real captures -----------------------------------------


def test_every_committed_capture_parses():
    """A capture that stopped parsing would silently drop a gold-set case."""
    found = sorted(EXAMPLES.glob("*.jsonl"))
    assert len(found) >= 4, f"expected the four committed captures, found {found}"
    for path in found:
        traj = load_governor_jsonl(path)
        assert traj.task_id.startswith("run_"), f"{path.name} lost its run id"
        assert traj.steps, f"{path.name} produced no steps"


def test_a_completed_run_reaches_its_terminal_step():
    traj = load_governor_jsonl(COMPLETED)
    assert traj.final_action == "completed"
    assert [s.tool for s in traj.tool_steps()] == [TERMINAL_STEP_NAME]


def test_a_halted_run_has_the_funded_steps_and_no_terminal_step():
    """The real partial-result case: work was done, the plan never closed."""
    traj = load_governor_jsonl(HALTED_AFTER_2)
    assert traj.final_action == "budget-preflight"
    tools = traj.tool_steps()
    assert [s.tool for s in tools] == ["writeup", "writeup"]
    # the two funded write-ups covered DIFFERENT advisories, so this is not a
    # redundant repeat even though the operation name is identical
    subjects = [s.args["subject"] for s in tools]
    assert subjects == ["GHSA-c83g-rgw3-j3cx:browserslist", "GHSA-73wf-gq98-2v4g:browserslist"]
    assert len(set(subjects)) == 2


def test_a_preflight_refusal_emits_no_tool_step():
    """A refused call is not a call.

    The governor priced step 0's worst case, found it did not fit the
    remaining budget, and never invoked the model. Emitting a tool step for
    it would report an action that did not happen.
    """
    traj = load_governor_jsonl(REFUSED_AT_0)
    assert traj.tool_steps() == []
    assert traj.final_action == "budget-preflight"
    # the reason the run stopped must still be visible to a reader
    assert any("refused step 0 pre-flight" in (s.text or "") for s in traj.steps)


def test_the_routing_decision_survives_into_the_trajectory():
    traj = load_governor_jsonl(HALTED_AFTER_1)
    thoughts = [s.text or "" for s in traj.steps if s.kind == "thought"]
    assert any("strong tier" in t and "confidence 0.40 below 0.6" in t for t in thoughts)


# --- the operation/subject split ------------------------------------------


def test_the_subject_is_split_out_of_the_step_name():
    """Without this split, `redundant_call_after_success` could never fire.

    budget-keeper names each step after its subject
    (`writeup:GHSA-xxx:browserslist`), so every step would look like a
    distinct tool and an identical repeat would be invisible.
    """
    events = [
        {"type": "run-start", "runId": "run_x", "budgetUsd": 1, "plannedSteps": 2},
        {
            "type": "step-start",
            "step": 0,
            "name": "writeup:GHSA-aaa:pkg",
            "model": "m",
            "tier": "mid",
        },
        {"type": "step-end", "step": 0, "name": "writeup:GHSA-aaa:pkg", "spend": {"usd": 1}},
        {
            "type": "step-start",
            "step": 1,
            "name": "writeup:GHSA-aaa:pkg",
            "model": "m",
            "tier": "mid",
        },
        {"type": "step-end", "step": 1, "name": "writeup:GHSA-aaa:pkg", "spend": {"usd": 1}},
        {"type": "run-end", "runId": "run_x", "reason": "completed", "spend": {"usd": 2}},
    ]
    traj = trajectory_from_governor_events(events)
    assert [s.tool for s in traj.tool_steps()] == ["writeup", "writeup"]
    report = grade(traj, [redundant_call_after_success])
    assert not report.passed
    assert report.violations[0].rule == "redundant_call_after_success"


def test_the_same_subject_at_a_different_tier_is_not_a_redundant_repeat():
    """An escalation is the router working, not over-calling.

    The tier is part of the args specifically so a retry at a stronger model
    is distinguishable from an identical repeat.
    """
    events = [
        {
            "type": "step-start",
            "step": 0,
            "name": "writeup:GHSA-aaa:pkg",
            "model": "cheap-1",
            "tier": "cheap",
        },
        {"type": "step-end", "step": 0, "name": "writeup:GHSA-aaa:pkg", "spend": {"usd": 1}},
        {
            "type": "step-start",
            "step": 1,
            "name": "writeup:GHSA-aaa:pkg",
            "model": "strong-1",
            "tier": "strong",
        },
        {"type": "step-end", "step": 1, "name": "writeup:GHSA-aaa:pkg", "spend": {"usd": 1}},
        {"type": "run-end", "runId": "run_x", "reason": "completed", "spend": {"usd": 2}},
    ]
    assert grade(trajectory_from_governor_events(events), [redundant_call_after_success]).passed


# --- malformed streams ----------------------------------------------------


def test_an_unpaired_step_start_is_an_error_not_a_dropped_step():
    """Silently dropping it would shorten the trajectory.

    A missing step could turn a genuine violation into a clean report, which
    is the worst available failure for an eval harness.
    """
    events = [
        {"type": "step-start", "step": 0, "name": "writeup:a:b", "model": "m", "tier": "mid"},
        {"type": "run-end", "runId": "run_x", "reason": "completed", "spend": {"usd": 0}},
    ]
    with pytest.raises(ValueError, match="still open"):
        trajectory_from_governor_events(events)


def test_overlapping_step_starts_are_an_error():
    events = [
        {"type": "step-start", "step": 0, "name": "a:x", "model": "m", "tier": "mid"},
        {"type": "step-start", "step": 1, "name": "b:y", "model": "m", "tier": "mid"},
    ]
    with pytest.raises(ValueError, match="still open"):
        trajectory_from_governor_events(events)


def test_a_step_end_with_no_open_step_is_an_error():
    events = [{"type": "step-end", "step": 0, "name": "a:x", "spend": {"usd": 1}}]
    with pytest.raises(ValueError, match="no open step-start"):
        trajectory_from_governor_events(events)


def test_an_unrecognised_event_type_is_an_error_not_ignored():
    """A new governor event must fail loudly rather than be dropped.

    If budget-keeper gains an event type that carries control flow, silently
    ignoring it would under-report the trajectory. Failing forces this
    adapter to be updated deliberately.
    """
    with pytest.raises(ValueError, match="unrecognised governor event"):
        trajectory_from_governor_events([{"type": "some-new-event", "step": 0}])


def test_killswitch_closes_the_open_step_as_failed():
    """Opposite of a pre-flight refusal: the call DID happen, then was cut off."""
    events = [
        {"type": "step-start", "step": 0, "name": "writeup:a:b", "model": "m", "tier": "strong"},
        {"type": "killswitch", "step": 0, "spentUsd": 0.5, "budgetUsd": 0.4},
        {"type": "run-end", "runId": "run_x", "reason": "killswitch", "spend": {"usd": 0.5}},
    ]
    traj = trajectory_from_governor_events(events)
    tools = traj.tool_steps()
    assert len(tools) == 1
    assert tools[0].ok is False
    assert "overran its allowance" in (tools[0].result or "")


def test_spend_telemetry_does_not_become_steps():
    events = [
        {"type": "step-start", "step": 0, "name": "writeup:a:b", "model": "m", "tier": "mid"},
        {"type": "spend", "step": 0, "spend": {"usd": 0.1}, "remainingUsd": 0.9},
        {"type": "spend", "step": 0, "spend": {"usd": 0.2}, "remainingUsd": 0.8},
        {"type": "step-end", "step": 0, "name": "writeup:a:b", "spend": {"usd": 0.2}},
        {"type": "allowance-exhausted", "step": 0, "outputTokenCap": 100},
        {"type": "run-end", "runId": "run_x", "reason": "completed", "spend": {"usd": 0.2}},
    ]
    traj = trajectory_from_governor_events(events)
    assert len(traj.tool_steps()) == 1


# --- the external-halt distinction the second subject forced ---------------


def test_a_budget_halt_is_not_scored_as_an_agent_process_failure():
    """Regression for a real false positive this second subject exposed.

    `no_terminal_action` fired on every budget-halted run, scoring the
    governor's correct refusal as the agent failing to commit. Both shapes
    look identical from the tool list alone; `final_action` is what tells
    them apart.
    """
    traj = load_governor_jsonl(HALTED_AFTER_2)
    strict = no_terminal_action(terminal_tools=frozenset({TERMINAL_STEP_NAME}))
    lenient = no_terminal_action(
        terminal_tools=frozenset({TERMINAL_STEP_NAME}),
        external_halt_actions=frozenset({"budget-preflight", "killswitch"}),
    )
    # the rule as originally written: fires
    assert not grade(traj, [strict]).passed
    # told which halts are external: stays silent
    assert grade(traj, [lenient]).passed


def test_an_agent_that_simply_stopped_is_still_caught():
    """The leniency must not become a blanket excuse.

    A run that completed normally without ever reaching its terminal step is
    the genuine process failure, and must still fire even for a caller that
    declared external halt reasons.
    """
    events = [
        {"type": "step-start", "step": 0, "name": "writeup:a:b", "model": "m", "tier": "mid"},
        {"type": "step-end", "step": 0, "name": "writeup:a:b", "spend": {"usd": 0.1}},
        {"type": "run-end", "runId": "run_x", "reason": "completed", "spend": {"usd": 0.1}},
    ]
    rule = no_terminal_action(
        terminal_tools=frozenset({TERMINAL_STEP_NAME}),
        external_halt_actions=frozenset({"budget-preflight", "killswitch"}),
    )
    report = grade(trajectory_from_governor_events(events), [rule])
    assert not report.passed
    assert report.violations[0].rule == "no_terminal_action"
