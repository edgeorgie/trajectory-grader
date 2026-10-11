# Calibration — rubric vs. human labels

Regenerate with:

```bash
python -m trajectory_grader.calibrate gold-set/ examples/subject-under-test/
```

## The number, and why it is not yet a result

**1 labeled trajectory. Raw agreement 4/4 rules. Cohen's kappa: undefined on every rule.**

That is not a good score. It is barely a measurement, and the honest reading
is that this project does not yet have a calibration result — it has working
calibration *machinery* and one real label to prove the machinery runs against
real data.

Kappa is undefined here for a specific, instructive reason: with one
trajectory, every verdict on both sides is `ok`, so expected-agreement-by-
chance is 1.0 and the formula divides by zero. Raw agreement reads 1.000.
Reporting that 1.000 as "100% agreement with human judgement" would be the
most flattering available lie, which is exactly why `cohens_kappa` returns
`None` and the CLI prints the word *undefined* instead of a number.

The target in `ROADMAP.md` is 20–30 labels. At that size kappa becomes
meaningful, and crucially the gold set will contain trajectories where rules
*should* fire — right now it contains none, so nothing here demonstrates the
rubric can discriminate at all.

## What the one label did find

Labeling a real trajectory by hand immediately found a false positive in the
rubric, which is the entire argument for doing this rather than trusting the
rules.

`redundant_call_after_success` fired on the real triage-desk run, reporting
that the agent called `submit_triage` twice with identical arguments. The raw
log does contain two such entries. But reading triage-desk's own agent loop
(`lib/agent.ts`, the two `onStep` calls bracketing `executeTool`) shows it
emits one step *before* executing a call and another *after*, both carrying
the same `call.id` — one action, logged twice.

So the rule was blaming the agent for its logger, and would have done so on
**every** single-call triage-desk run. Fixed in the adapter
(`adapters/triage_desk.py`, `_coalesce_tool_steps`) rather than in the rule,
because normalising a source format's quirks is the adapter's job; weakening
the rule would have taught it to ignore genuine duplicate calls too. A test
asserts a real repeat call (distinct `id`) is still caught, and another pins
the upstream double-logging so the normalisation can be retired if triage-desk
ever changes.

Note what this means for the agreement number above: the 4/4 is *post-fix*.
Pre-fix it was 3/4, and the disagreement was the rubric's fault, not the
label's.

## Method

- Labels live in `gold-set/*.json`, one file per trajectory, verdicts recorded
  per rule name so agreement is reported per rule — a judge that is strong on
  one rule and useless on another is the interesting case, and a single
  blended number hides it.
- Every label requires `labeled_by` and `labeled_at`. An unauditable gold
  label is worth less than none, so these are validation errors, not optional
  fields.
- `unclear` is a first-class verdict and is excluded from scoring. Forcing a
  genuine judgement call into ok/violation to keep the denominator tidy is how
  a gold set stops being trustworthy.
- Labeled trajectories with no corresponding graded run are listed separately
  by the CLI rather than dropped, so a shrinking denominator stays visible.
- Labels are written by hand. Nothing in this repo infers them, by design: the
  gold set's only purpose is to be an independent reference for the thing
  being measured, and a reference produced by the system under evaluation
  measures self-consistency, not correctness.

## Honest limitations

- **n=1.** Stated above; the headline number means almost nothing yet.
- **No positive cases.** Every verdict in the gold set is `ok`. Until a
  trajectory that genuinely violates a rule is labeled, the gold set cannot
  distinguish a working rule from one that never fires.
- **One subject under test.** Only triage-desk's loop has been graded. A
  second, independently-built agent would materially strengthen the
  "process eval, not self-grading" claim.
- **Single labeler.** Inter-*rater* agreement (two humans) is not measured at
  all; this is human-vs-rubric only. With one labeler, systematic bias in the
  labels is invisible.
- **No LLM judge yet.** These numbers describe the deterministic rule engine.
  The judge, and its own calibration, is separate future work.
