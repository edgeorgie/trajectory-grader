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
  they are coalesced here — see ``_coalesce_tool_steps``.

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


def _is_pre_execution_pair(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Whether two consecutive tool steps are one call logged pre- and post-execution.

    All four conditions must hold, because each one alone is satisfiable by a
    pair of genuinely distinct actions:

    1. both carry an ``id`` field and the ids are equal — but note the id
       alone is NOT sufficient evidence: triage-desk's own
       ``scripts/triage-bot.ts`` hardcodes ``id: "heuristic-1"`` for every
       heuristic run, and ``lib/agent.ts`` falls back to ``id: b.id ?? ""``
       when a model omits one, so ids genuinely repeat across distinct calls;
    2. the tool ``name`` matches — a same-id pair naming two different tools
       is two actions, and merging them would silently DELETE one, which is
       the signal rules like ``wrong_tool_before_right`` exist to detect;
    3. the ``input`` matches — same tool, different args is two calls;
    4. the first has no ``output`` and the second does — this is the actual
       shape of the pre/post pair, and it is what distinguishes it from a
       genuine immediate repeat (where BOTH records carry an outcome).

    Condition 4 is the load-bearing one. Keyed on ``id`` alone, a real
    duplicate call that reused an id would be silently collapsed and the
    rubric would report a clean trajectory.
    """
    if "id" not in first or "id" not in second or first["id"] != second["id"]:
        return False
    if first.get("name") != second.get("name"):
        return False
    if first.get("input") != second.get("input"):
        return False
    # the pre-execution record has no outcome yet; the post-execution one does
    return "output" not in first and "output" in second


def _coalesce_tool_steps(raw_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge triage-desk's pre/post-execution step pair into one action.

    Only merges a pair that looks like one call logged twice around its own
    execution (see :func:`_is_pre_execution_pair`). Everything else — a
    genuine repeat, two different tools that happen to share an id, a
    retry — passes through as separate steps, so the rubric still sees it.
    """
    merged: list[dict[str, Any]] = []
    for raw in raw_steps:
        if (
            raw.get("kind") == "tool"
            and merged
            and merged[-1].get("kind") == "tool"
            and _is_pre_execution_pair(merged[-1], raw)
        ):
            # same call, logged again after execution — keep the richer record
            merged[-1] = {**merged[-1], **raw}
            continue
        merged.append(raw)
    return merged
