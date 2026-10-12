"""Declarative rubric: a plain list of named rule checks.

Each rule is a function (Trajectory) -> list[Violation]. Keeping rules as
small, independent, pure functions (rather than one monolithic scorer) is
what makes "which rule fired and why" legible in a report, and what makes
each rule independently unit-testable.

This is intentionally NOT an LLM-judge. It's a deterministic rule engine.
See ROADMAP.md for why the judge is future work, not faked here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .schema import Trajectory


@dataclass(frozen=True)
class Violation:
    rule: str
    step_index: int
    message: str


Rule = Callable[[Trajectory], list[Violation]]


def wrong_tool_before_right(*, wrong_tool: str, right_tool: str) -> Rule:
    """Flag calling `wrong_tool` before ever calling `right_tool`, when
    `right_tool` was eventually called in the same trajectory (i.e. the
    agent itself demonstrated the right tool was reachable/known)."""

    def check(traj: Trajectory) -> list[Violation]:
        tools = traj.tool_steps()
        right_called = any(s.tool == right_tool for s in tools)
        if not right_called:
            return []
        violations = []
        for i, s in enumerate(tools):
            if s.tool == wrong_tool:
                violations.append(
                    Violation(
                        rule="wrong_tool_before_right",
                        step_index=i,
                        message=(
                            f"called '{wrong_tool}' before '{right_tool}' was ever used, "
                            f"even though '{right_tool}' was used later in this trajectory"
                        ),
                    )
                )
            if s.tool == right_tool:
                break
        return violations

    return check


def bad_retry_no_change(traj: Trajectory) -> list[Violation]:
    """Flag a failed tool call being retried with identical args.

    A sensible retry changes something (different args, or a different
    tool). Retrying the exact same call after it already failed is a
    process-quality smell: the agent didn't use the error to adapt.
    """
    violations: list[Violation] = []
    tools = traj.tool_steps()
    for i in range(1, len(tools)):
        prev, cur = tools[i - 1], tools[i]
        if not prev.ok and cur.tool == prev.tool and cur.args == prev.args:
            violations.append(
                Violation(
                    rule="bad_retry_no_change",
                    step_index=i,
                    message=(
                        f"retried '{cur.tool}' with identical args after it failed; "
                        "a sensible retry changes the args or tries a different tool"
                    ),
                )
            )
    return violations


def redundant_call_after_success(traj: Trajectory) -> list[Violation]:
    """Flag an identical successful tool call being repeated.

    Once a call has succeeded, repeating the exact same (tool, args) pair
    again adds no new information — it's over-calling.
    """
    violations: list[Violation] = []
    seen_successful: set[tuple[str, str]] = set()
    for i, s in enumerate(traj.tool_steps()):
        key = (s.tool or "", _stable_args_key(s.args))
        if key in seen_successful:
            violations.append(
                Violation(
                    rule="redundant_call_after_success",
                    step_index=i,
                    message=f"repeated an already-successful call to '{s.tool}' with the same args",
                )
            )
        elif s.ok:
            seen_successful.add(key)
    return violations


def no_terminal_action(
    *,
    terminal_tools: frozenset[str],
    external_halt_actions: frozenset[str] = frozenset(),
) -> Rule:
    """Flag a trajectory that never calls any tool in `terminal_tools`.

    A trajectory that only ever investigates and never acts (e.g. never
    calls submit/reply/close) stopped at the wrong point — it should either
    have taken the terminal action or explicitly asked for clarification.

    `external_halt_actions` names the `final_action` values that mean the
    run was stopped by something outside the agent's own judgement, in which
    case this rule stays silent. It exists because grading a second,
    independently-built agent showed the rule as originally written could
    not tell two very different situations apart:

    1. an agent that wandered, lost the thread, and stopped without
       committing — the process failure this rule is for;
    2. a run that a cost governor deliberately halted on a budget ceiling,
       having correctly priced the next step and refused it.

    Both produce a trajectory with no terminal call, so the rule fired on
    both. But (2) is the governor working exactly as designed, and scoring
    it as an agent process failure is the same category of error as blaming
    an agent for its logger double-writing steps (see CALIBRATION.md) — the
    rule was attributing to the agent an outcome the agent did not choose.

    Defaulting to an empty set keeps the original behaviour for callers that
    have no such concept, so an adapter must opt in by naming its own halt
    reasons rather than getting silent leniency.
    """

    def check(traj: Trajectory) -> list[Violation]:
        tools = traj.tool_steps()
        if any(s.tool in terminal_tools for s in tools):
            return []
        if traj.final_action is not None and traj.final_action in external_halt_actions:
            return []
        last_index = max(len(tools) - 1, 0)
        return [
            Violation(
                rule="no_terminal_action",
                step_index=last_index,
                message=(
                    f"trajectory never called a terminal tool ({sorted(terminal_tools)}); "
                    "it investigated but never committed to an outcome"
                ),
            )
        ]

    return check


def _stable_args_key(args: dict[str, Any]) -> str:
    """Order-independent fingerprint of a tool call's arguments.

    Used to decide whether two calls to the same tool were *identical*
    (a redundant repeat / an unchanged retry) rather than merely adjacent.
    """
    return repr(sorted(args.items()))
