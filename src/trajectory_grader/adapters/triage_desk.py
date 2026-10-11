"""Converts edgeorgie/triage-desk's run-log JSON format into the canonical
Trajectory schema used by this grader.

triage-desk is used here purely as a real, independently-built subject
under test, to exercise the adapter + grader against a real log instead of
only synthetic fixtures. It is NOT used to validate that the rubric rules
are correct — the unit tests in tests/test_rubric.py do that with small,
deliberately constructed synthetic trajectories.

triage-desk's log shape (see triage-logs/runs.jsonl in that repo):
    {
      "ts": "...", "repo": "...", "issue": 24, "mode": "heuristic",
      "result": {...the final submitted triage...},
      "steps": [
        {"kind": "thought", "text": "..."},
        {"kind": "tool", "id": "...", "name": "submit_triage", "input": {...}, "output": "..."}
      ]
    }

Differences from the canonical schema handled here:
- triage-desk calls the tool name field "name", the canonical schema calls
  it "tool".
- triage-desk calls the tool input field "input", the canonical schema
  calls it "args".
- triage-desk doesn't record a pass/fail flag per step; it records
  ``isError`` on the post-execution step, and absence of it is treated as
  success.
- **One tool call appears as two log steps.** triage-desk's agent loop
  (``lib/agent.ts``, the two ``onStep`` calls around ``executeTool``) emits
  a step *before* executing a call and another *after* it, both carrying
  the same ``id``; only the second has ``output``. Those are one action, so
  they are coalesced here by ``id`` — see ``_coalesce_tool_steps``.

  This matters beyond tidiness: treating them as two steps made the
  ``redundant_call_after_success`` rule fire on every single-call
  triage-desk run, reporting a process flaw that the agent never committed.
  Normalising a source format's logging shape is the adapter's job, and
  doing it in the rubric instead would have taught the rule to ignore real
  duplicate calls as well as artefactual ones.
"""

from __future__ import annotations

from typing import Any

from ..schema import Step, Trajectory


def trajectory_from_triage_desk_log(entry: dict[str, Any]) -> Trajectory:
    steps = []
    for raw in _coalesce_tool_steps(entry["steps"]):
        if raw["kind"] == "thought":
            steps.append(Step(kind="thought", text=raw.get("text")))
        elif raw["kind"] == "tool":
            steps.append(
                Step(
                    kind="tool",
                    tool=raw["name"],
                    args=raw.get("input", {}),
                    result=raw.get("output"),
                    ok=not raw.get("isError", False) and "error" not in raw,
                )
            )
        else:
            raise ValueError(f"unknown triage-desk step kind: {raw['kind']!r}")

    result = entry.get("result", {})
    final_action = result.get("kind") if result else None
    return Trajectory(
        task_id=f"triage-desk-issue-{entry['issue']}",
        agent_name="edgeorgie/triage-desk",
        steps=tuple(steps),
        final_action=final_action,
    )


def _coalesce_tool_steps(raw_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge triage-desk's pre/post-execution step pair into one action.

    Consecutive ``tool`` steps sharing an ``id`` are the same call logged
    twice (before and after execution); the later one carries the outcome,
    so it wins. Thought steps and steps with no ``id`` pass through
    untouched.

    Deliberately scoped to *consecutive* steps with an identical ``id``: a
    genuine second call to the same tool gets a fresh ``id`` from the model,
    so a real duplicate is still preserved and still caught by the rubric.
    """
    merged: list[dict[str, Any]] = []
    for raw in raw_steps:
        if (
            raw.get("kind") == "tool"
            and raw.get("id")
            and merged
            and merged[-1].get("kind") == "tool"
            and merged[-1].get("id") == raw["id"]
        ):
            # same call, logged again after execution — keep the richer record
            merged[-1] = {**merged[-1], **raw}
            continue
        merged.append(raw)
    return merged
