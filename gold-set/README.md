# Gold set — hand-labeled reference trajectories

Human labels that the rubric (and, later, an LLM judge) is measured
*against*. One JSON file per trajectory.

**Current size: 1 label.** That is enough to prove the calibration path runs
end to end against real data and nowhere near enough to publish an agreement
number from — see `../CALIBRATION.md`, which says so plainly. The target is
20–30 (`../ROADMAP.md`).

## Why nothing here is generated

These labels are the independent reference. A reference produced by the same
kind of system being evaluated would measure self-consistency, not
correctness, so this repo contains no label *inference* — only a schema, a
loader, and validation (`src/trajectory_grader/labels.py`). Writing the
verdicts is a human step, deliberately.

It already earned its keep: labeling the first trajectory by hand surfaced a
false positive in `redundant_call_after_success` that would have fired on
every single-call triage-desk run (details in `../CALIBRATION.md`).

## File format

```json
{
  "task_id": "triage-desk-issue-24",
  "labeled_by": "edgeorgie",
  "labeled_at": "2026-10-11",
  "notes": "why each verdict was chosen, especially the judgement calls",
  "verdicts": {
    "wrong_tool_before_right": "ok",
    "redundant_call_after_success": "violation"
  }
}
```

- `task_id` must match the trajectory's `task_id` as the adapter produces it,
  or the label is reported as orphaned and excluded from every denominator.
- `labeled_by` / `labeled_at` are **required**. An unauditable gold label is
  worth less than none.
- A verdict is `ok`, `violation`, or `unclear`. `unclear` is first-class and
  excluded from scoring — forcing a genuine judgement call into a verdict to
  keep the denominator tidy is how a gold set stops being trustworthy.
- Verdicts are recorded per rule name so agreement can be reported per rule.
- Two labels for one `task_id` is a load error, not a silent double-count.

## Reporting agreement

```bash
python -m trajectory_grader.calibrate gold-set/ examples/subject-under-test/
```

Prints raw agreement and Cohen's kappa per rule, plus every individual
disagreement. Exits 2 on an empty gold set rather than printing a vacuous
1.000.

Both numbers are published because either alone misleads: raw agreement
flatters a rule that never fires, and kappa is undefined (not 1.0) when both
sides used a single category — which is exactly the state a small gold set is
in. `CALIBRATION.md` must keep stating the label count next to the number.
