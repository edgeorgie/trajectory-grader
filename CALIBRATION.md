# Calibration — rubric vs. human labels

Regenerate with:

```bash
python -m trajectory_grader.calibrate gold-set/ examples/subject-under-test/
```

## The number, and why it is not yet a result

**1 labeled trajectory. Raw agreement 4/4 rules. Cohen's kappa: withheld on every rule.**

That is not a good score. It is barely a measurement, and the honest reading
is that this project does not yet have a calibration result — it has working
calibration *machinery* and one real label to prove the machinery runs against
real data.

Kappa is withheld here for two separate reasons, both worth stating because
they mean different things. With one trajectory, every verdict on both sides
is `ok`, so expected-agreement-by-chance is 1.0 and the formula divides by
zero. Independently, n=1 is below the `n>=5` floor the tool enforces: at that
size the formula is happy to emit a confident-looking `0.000` (with a single
disagreement, pe = 0 and kappa = 0 exactly), which reads as "measured,
agreement no better than chance" when it is one item. Raw agreement reads
1.000. Reporting that 1.000 as "100% agreement with human judgement" would be
the most flattering available lie, which is why the tool prints the reason it
withheld the number instead.

The target in `ROADMAP.md` is 20–30 labels. At that size kappa becomes
meaningful, and crucially the gold set will contain trajectories where rules
*should* fire — right now it contains none, so nothing here demonstrates the
rubric can discriminate at all.

**Four unlabeled real trajectories are committed and waiting** under
`examples/subject-under-test/budget-keeper/`, three of which are cases where
a rule genuinely should fire. They are not labeled because labeling is a
human step by design (see Method below) — this repo infers nothing. That is
the bottleneck, and it is named rather than worked around.

## What the labels have found so far

Two real false positives, both found by checking the rubric against reality
rather than trusting it. This is the entire argument for doing calibration at
all, and neither was findable from the rubric's own unit tests — those pass
on synthetic trajectories built to match what the rule already believes.

### 1. Blaming an agent for its logger (found by hand-labeling)

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
the rule would have taught it to ignore genuine duplicate calls too.

The first version of that fix then introduced a worse bug by keying the merge
on `id` alone, on the assumption that a genuine second call always gets a
fresh id. That assumption is false — `scripts/triage-bot.ts` hardcodes
`id: "heuristic-1"` for every heuristic run, and `lib/agent.ts` falls back to
`id: b.id ?? ""`. An id-keyed merge therefore *deleted* real tool calls and
silently collapsed genuine duplicates. The merge now requires the pre/post
shape specifically: same id, same tool, same input, and an outcome on the
second record only.

Note what this means for the agreement number above: the 4/4 is *post-fix*.
Pre-fix it was 3/4, and the disagreement was the rubric's fault, not the
label's.

### 2. Scoring a cost governor's correct refusal as an agent failure

Found by adding a **second subject under test**
([budget-keeper](https://github.com/edgeorgie/budget-keeper), a patch-plan
agent under a hard USD ceiling) — and findable no other way, because
triage-desk has no concept of being stopped by anything outside itself.

`no_terminal_action` fired on every budget-halted run. The trajectory looks
exactly like the failure the rule is for: steps were taken, no terminal
action was ever called. But the reason is the opposite of a process failure —
the governor priced the next step's worst case, found it did not fit the
remaining budget, and refused it. That is the governor working precisely as
designed, and the run that *should* score badly is the one that burns the
whole budget and still commits nothing.

Both shapes are indistinguishable from the tool list alone. `final_action` is
what separates them, so the rule now takes `external_halt_actions` naming the
halt reasons that are not the agent's own judgement. It defaults to empty, so
an adapter must opt in rather than receive silent leniency, and a test
asserts an agent that *merely stopped* is still caught.

This is the same category of error as (1): attributing to the agent an
outcome the agent did not choose.

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
  distinguish a working rule from one that never fires. Four unlabeled real
  trajectories are now committed specifically to close this, three of them
  cases where a rule should fire; labeling them is the remaining human step.
- **Single labeler.** Inter-*rater* agreement (two humans) is not measured at
  all; this is human-vs-rubric only. With one labeler, systematic bias in the
  labels is invisible.
- **No LLM judge yet.** These numbers describe the deterministic rule engine.
  The judge, and its own calibration, is separate future work.
- **The budget-keeper captures' dollar figures are simulated.** That agent
  ran without an API key, so its token/cost numbers come from its own
  deterministic simulator. The control flow this harness actually grades —
  planned, funded, refused, stopped — is real. Stated again here because a
  caveat that lives only in the examples README gets lost the moment a number
  is quoted elsewhere.

