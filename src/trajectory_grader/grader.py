"""Runs a rubric (list of rule checks) over a trajectory and builds a report."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .rubric import Violation
from .schema import Trajectory

RuleFn = Callable[[Trajectory], list[Violation]]


@dataclass(frozen=True)
class Report:
    task_id: str
    agent_name: str
    violations: tuple[Violation, ...]
    num_tool_calls: int

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0

    def summary(self) -> str:
        lines = [
            f"Trajectory Grader report for task={self.task_id!r} agent={self.agent_name!r}",
            f"tool calls: {self.num_tool_calls}  violations: {len(self.violations)}",
        ]
        for v in self.violations:
            lines.append(f"  [{v.rule}] step {v.step_index}: {v.message}")
        if not self.violations:
            lines.append("  (no rubric violations found by the rules run)")
        return "\n".join(lines)


def grade(trajectory: Trajectory, rules: list[RuleFn]) -> Report:
    """Run every rule against the trajectory and collect all violations.

    Deliberately not an aggregate numeric score (yet): a single number
    hides which specific process issue occurred, and this project's whole
    point is making process issues visible, not compressing them away.
    """
    violations: list[Violation] = []
    for rule in rules:
        violations.extend(rule(trajectory))
    return Report(
        task_id=trajectory.task_id,
        agent_name=trajectory.agent_name,
        violations=tuple(violations),
        num_tool_calls=len(trajectory.tool_steps()),
    )
