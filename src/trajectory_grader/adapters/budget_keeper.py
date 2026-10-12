"""Adapter for budget-keeper's governor event stream.

Second subject under test, added specifically to stop this harness from
being validated against a single agent's log format. ``triage_desk.py``
converts a *step list* that the agent itself assembled; this one converts an
*event stream* emitted by a cost governor, which is a materially different
shape:

- Events are not steps. One governed step produces a ``step-start`` and then
  exactly one of ``step-end`` / ``step-error``, with any number of ``spend``
  events interleaved. Pairing them is this adapter's main job.
- Some events describe an action that **did not happen**:
  ``preflight-refusal`` means the governor priced the step's worst case,
  found it did not fit in the remaining budget, and declined to call the
  model at all. Nothing executed, so it is deliberately NOT emitted as a
  tool step — a refused call is not a call. It becomes a thought step, so
  the reason the trajectory stops is still visible to a reader of the
  canonical form without inventing a tool call that never ran.
- ``killswitch`` is the opposite case: the provider was called, overran its
  allowance mid-stream, and was cut off. Something did execute, so the
  in-flight step is closed as failed.

What is real and what is not, stated plainly: budget-keeper runs in
``simulated`` inference mode unless ``ANTHROPIC_API_KEY`` is set, so the
token counts and dollar figures inside these events come from its
deterministic simulator rather than a provider bill. The **control flow** —
which steps were planned, which ran, which were refused, in what order, and
where the run stopped — is produced by the real governor either way, and
that control flow is the only thing this harness grades. A trajectory is a
sequence of decisions; the simulator does not fabricate the sequence.

Terminal action: budget-keeper's ``buildSteps`` emits one ``writeup:*`` step
per vulnerable dependency and then always appends a final ``roll-up`` step
(``src/task/patch-plan.ts``). So ``roll-up`` is the one step that commits an
outcome, and a run that stops before reaching it produced write-ups that
were never synthesised into a plan.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schema import Step, Trajectory

#: The step name budget-keeper always appends last, as its committed outcome.
#: Exposed so a rubric can be configured with it rather than hardcoding the
#: string at the call site.
TERMINAL_STEP_NAME = "roll-up"

#: Event types that carry no trajectory information. ``spend`` fires on every
#: streamed chunk (hundreds per run) and is pure telemetry; the step it
#: belongs to is already represented by its start/end pair.
_IGNORED_EVENT_TYPES = frozenset({"spend", "allowance-exhausted", "run-start"})


def _tool_name(step_name: str) -> str:
    """Collapse a governed step's name to the operation it performs.

    Step names embed their subject (``writeup:GHSA-c83g-rgw3-j3cx:browserslist``),
    which makes every step look like a distinct tool and would stop
    ``redundant_call_after_success`` from ever being able to fire. The
    operation is the part before the first colon; the subject belongs in the
    args, where the rubric compares it.
    """
    return step_name.split(":", 1)[0]


def _step_args(step_name: str, event: dict[str, Any]) -> dict[str, Any]:
    """Args for a governed step: its subject plus the routing decision.

    The model/tier is included because two calls to the same operation on the
    same subject at *different* tiers are not a redundant repeat — they are an
    escalation, which is the behaviour budget-keeper's router exists to
    perform.
    """
    args: dict[str, Any] = {"subject": step_name.split(":", 1)[1] if ":" in step_name else ""}
    for key in ("model", "tier"):
        if key in event:
            args[key] = event[key]
    return args


def trajectory_from_governor_events(
    events: list[dict[str, Any]],
    *,
    task_id: str | None = None,
    agent_name: str = "budget-keeper",
) -> Trajectory:
    """Convert a governor event stream into the canonical schema.

    ``task_id`` defaults to the run id carried by the stream's ``run-start`` /
    ``run-end`` events, so a trajectory is identified by the thing that
    actually produced it rather than by a filename.

    Raises ``ValueError`` on a stream whose step events do not pair up —
    silently dropping an unpaired ``step-start`` would shorten the trajectory
    and could turn a real violation into a clean report.
    """
    steps: list[Step] = []
    run_id: str | None = None
    final_action: str | None = None
    open_step: dict[str, Any] | None = None

    for event in events:
        kind = event.get("type")
        if kind in ("run-start", "run-end"):
            run_id = run_id or event.get("runId")

        if kind == "tier-decision":
            steps.append(
                Step(
                    kind="thought",
                    text=(
                        f"routing step {event.get('step')} to the "
                        f"{event.get('chosen')} tier: {event.get('reason')}"
                    ),
                )
            )
        elif kind == "step-start":
            if open_step is not None:
                raise ValueError(
                    f"step-start for step {event.get('step')} while step "
                    f"{open_step.get('step')} is still open; the stream is malformed"
                )
            open_step = event
        elif kind in ("step-end", "step-error", "killswitch"):
            if open_step is None:
                raise ValueError(f"{kind} for step {event.get('step')} with no open step-start")
            name = str(open_step.get("name", ""))
            steps.append(
                Step(
                    kind="tool",
                    tool=_tool_name(name),
                    args=_step_args(name, open_step),
                    result=_outcome_text(kind, event),
                    ok=kind == "step-end",
                )
            )
            open_step = None
        elif kind == "preflight-refusal":
            # Priced, declined, never called. Not a tool step — see module docstring.
            steps.append(
                Step(
                    kind="thought",
                    text=(
                        f"refused step {event.get('step')} pre-flight: worst case "
                        f"${event.get('worstCaseUsd')} exceeds "
                        f"${event.get('remainingUsd')} remaining"
                    ),
                )
            )
        elif kind == "run-end":
            final_action = str(event.get("reason", "")) or None
        elif kind not in _IGNORED_EVENT_TYPES:
            raise ValueError(f"unrecognised governor event type {kind!r}")

    if open_step is not None:
        raise ValueError(
            f"stream ends with step {open_step.get('step')} still open; a truncated "
            "stream would under-report the trajectory"
        )

    return Trajectory(
        task_id=task_id or run_id or "unknown-run",
        agent_name=agent_name,
        steps=tuple(steps),
        final_action=final_action,
    )


def _outcome_text(kind: str, event: dict[str, Any]) -> str:
    if kind == "step-end":
        spend = event.get("spend", {})
        truncated = " (truncated)" if event.get("truncated") else ""
        return f"ok, ${spend.get('usd')}{truncated}"
    if kind == "killswitch":
        return (
            f"killed: provider overran its allowance, spent ${event.get('spentUsd')} "
            f"against a ${event.get('budgetUsd')} budget"
        )
    return f"failed: {event.get('message')}"


def load_governor_jsonl(path: Path, **kwargs: Any) -> Trajectory:
    """Read a governor event stream from a JSONL file.

    One JSON object per line, which is exactly what ``budget-keeper --json``
    writes to stdout. Blank lines are skipped; a malformed line raises rather
    than being dropped.
    """
    with open(path, encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    return trajectory_from_governor_events(events, **kwargs)
