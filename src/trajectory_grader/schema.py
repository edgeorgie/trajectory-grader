"""Canonical trajectory schema: the format all adapters convert into.

A trajectory is just an ordered list of steps an agent took while working a
single task. Keeping this format deliberately small (tool name, args, result,
ok/error flag, optional thought text) is what lets the same rubric run over
logs produced by completely different agents/frameworks, as long as there's
an adapter that maps their log format onto this one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Step:
    """One action in a trajectory.

    kind: "thought" (no tool call, just reasoning text) or "tool" (a tool
    call with its result).
    """

    kind: str
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    result: str | None = None
    ok: bool = True
    text: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("thought", "tool"):
            raise ValueError(f"Step.kind must be 'thought' or 'tool', got {self.kind!r}")
        if self.kind == "tool" and not self.tool:
            raise ValueError("a 'tool' step must have a tool name")


@dataclass(frozen=True)
class Trajectory:
    """A single recorded agent run: metadata plus its ordered steps."""

    task_id: str
    agent_name: str
    steps: tuple[Step, ...]
    final_action: str | None = None

    def tool_steps(self) -> list[Step]:
        return [s for s in self.steps if s.kind == "tool"]


def trajectory_from_dict(data: dict[str, Any]) -> Trajectory:
    """Build a Trajectory from the canonical JSON dict shape.

    Expected shape:
        {
          "task_id": str,
          "agent_name": str,
          "final_action": str | None,
          "steps": [
            {"kind": "thought", "text": "..."},
            {"kind": "tool", "tool": "...", "args": {...}, "result": "...", "ok": true}
          ]
        }
    """
    steps = tuple(
        Step(
            kind=s["kind"],
            tool=s.get("tool"),
            args=s.get("args", {}),
            result=s.get("result"),
            ok=s.get("ok", True),
            text=s.get("text"),
        )
        for s in data["steps"]
    )
    return Trajectory(
        task_id=data["task_id"],
        agent_name=data["agent_name"],
        steps=steps,
        final_action=data.get("final_action"),
    )
