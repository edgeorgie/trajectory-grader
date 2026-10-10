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
- triage-desk doesn't record a pass/fail flag per step; absence of an
  "error" key is treated as success (ok=True), since the real log sample
  available does not contain a recorded tool failure.
"""

from __future__ import annotations

from typing import Any

from ..schema import Step, Trajectory


def trajectory_from_triage_desk_log(entry: dict[str, Any]) -> Trajectory:
    steps = []
    for raw in entry["steps"]:
        if raw["kind"] == "thought":
            steps.append(Step(kind="thought", text=raw.get("text")))
        elif raw["kind"] == "tool":
            steps.append(
                Step(
                    kind="tool",
                    tool=raw["name"],
                    args=raw.get("input", {}),
                    result=raw.get("output"),
                    ok="error" not in raw,
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
