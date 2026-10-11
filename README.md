# Trajectory Grader

[![verify](https://github.com/edgeorgie/trajectory-grader/actions/workflows/verify.yml/badge.svg)](https://github.com/edgeorgie/trajectory-grader/actions/workflows/verify.yml)

**Status: early, actively-developing project. Not a finished product.
No benchmark numbers are claimed anywhere in this repo yet. Any numbers you
see below are counts of tests that were actually run, not accuracy/quality
scores for any agent.**

## What this is

Most agent "evals" score the final answer and throw away everything that
happened to get there. That hides the interesting failures: an agent that
called the wrong tool first and recovered, one that retried a failed call
with the exact same bad arguments forever, one that got the right answer but
only after six redundant tool calls past the point where it already had
enough information.

Trajectory Grader scores the **sequence of tool calls** an agent made — not
just whether it was eventually right — against a small, explicit, declarative
rubric. The goal is a harness that can take any recorded agent trajectory
(a list of `{tool, args, result, ok}` steps) and flag process-quality issues
like:

- calling a clearly-wrong tool before the right one, when the inputs already
  pointed at the right tool
- retrying a failed tool call without changing anything (vs. a sensible
  retry that adjusts the args)
- redundant/duplicate calls after the agent already had what it needed
  ("over-calling")
- stopping too early (no terminal action ever taken)

This is deliberately narrow in scope: a canonical trajectory format, a small
rule engine, a handful of rubric checks with real unit tests, and a working
calibration path that measures the rubric against hand-written human labels.
It is **not** yet: an LLM-judge, nor calibrated against a gold set large
enough for the agreement number to mean much — there is exactly **1** label
today against a target of 20–30. [CALIBRATION.md](./CALIBRATION.md) reports
that honestly instead of publishing the flattering number n=1 produces. See
[ROADMAP.md](./ROADMAP.md) for exactly what's missing and why it isn't done
in one sitting.

## Why this exists (and why it's not "another eval-lab")

This project exists specifically to evaluate *process*, which is a different
problem from scoring final-answer correctness. The subject-under-test for
the first real example is
[edgeorgie/triage-desk](https://github.com/edgeorgie/triage-desk)'s agent
loop — an existing, independently-built GitHub issue triage agent. Its logs
are used here purely as **the thing being evaluated**, not as proof that the
grader works. The grader's own test suite is the thing that proves the
grader works, and those tests use small synthetic trajectories designed to
exercise specific rubric rules, not triage-desk's output.

## Project layout

```
src/trajectory_grader/
  schema.py      canonical Step / Trajectory types + JSON loader
  rubric.py      declarative rubric: a list of named rule checks
  grader.py      runs a rubric against a trajectory, returns a report
  cli.py         grades a canonical trajectory file; documented exit codes
  labels.py      gold-label schema + loader/validation (no label inference,
                 by design — see gold-set/README.md)
  agreement.py   raw agreement + Cohen's kappa, per rubric rule
  calibrate.py   CLI: reports rubric-vs-human agreement over the gold set
  adapters/
    triage_desk.py   converts edgeorgie/triage-desk's run-log JSON format
                      into the canonical Trajectory schema
scripts/
  to_canonical.py   adapter CLI: raw triage-desk log -> canonical JSON on
                    stdout. Committed (rather than inlined in the workflow)
                    so the exact command CI runs is runnable locally.
tests/           unit tests for schema, rubric rules, the grader, the
                 adapter, the gold-label loader, agreement/kappa, and the
                 CLI's exit-code contract
examples/
  subject-under-test/   a real triage-desk run log, used as a worked example
gold-set/        hand-written human labels (1 today, target 20-30) + the
                 rules for writing them. See CALIBRATION.md for the numbers.
.github/workflows/
  verify.yml     the single required status check for this repo
```

## Quickstart

Requires Python 3.11+, no external dependencies for the core package.

```bash
cd trajectory-grader
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Grade the committed real example end-to-end (adapter → canonical schema → CLI):

```bash
python scripts/to_canonical.py \
  examples/subject-under-test/triage-desk-run-issue24.json > canonical.json
python -m trajectory_grader.cli canonical.json
```

The CLI's exit code is part of its contract, so it works as a CI gate on a
recorded trajectory:

| exit | meaning |
|------|---------|
| `0`  | no rubric rule fired |
| `1`  | at least one rule fired (report lists which rule, at which step) |
| `2`  | usage error, or the trajectory file is unreadable/malformed |

On the committed example this currently exits `0`. It did **not** at first:
the grader reported a `redundant_call_after_success` violation, and labeling
the trajectory by hand showed that was the grader's bug, not the agent's —
triage-desk logs each tool call twice (before and after execution, same
`call.id`), so the "duplicate" came from its logger. Fixed in the adapter;
the story is written up in [CALIBRATION.md](./CALIBRATION.md) because finding
it is the clearest argument for keeping a human-labeled gold set at all.

## Calibration: is the rubric's opinion any good?

```bash
python -m trajectory_grader.calibrate gold-set/ examples/subject-under-test/
```

Reports, per rule, raw agreement and Cohen's kappa against the hand-written
labels in `gold-set/`, plus every individual disagreement. Both numbers are
published because either alone misleads: raw agreement flatters a rule that
never fires, and kappa catches exactly that — it is `undefined` (not `1.0`)
when both sides only ever used one category.

**Today: 1 label, raw agreement 4/4 rules, kappa undefined on every rule.**
That is machinery working, not a result. [CALIBRATION.md](./CALIBRATION.md)
states the limitation at the top rather than leading with the 1.000.
`calibrate` exits `2` on an empty gold set rather than printing a vacuous
perfect score.

## Continuous integration

Every push and pull request to `main` runs the `verify` workflow
(`.github/workflows/verify.yml`). The real work happens in a `test` matrix on
Python 3.11 and 3.13:

- `ruff check` (lint) and `ruff format --check` (formatting)
- `mypy --strict` over `src/`
- the full `pytest` suite
- the CLI contract: `--help` exits `0`, and the real example trajectory
  above is graded without crashing
- the calibration contract: the hand-written gold set loads and agreement is
  reportable, so a typo in a label fails CI rather than silently skewing a
  published number
- a wheel build, then an import of that wheel from a clean virtualenv

A separate one-step `verify` job aggregates that matrix into a single fixed
status name. This is not ceremony: GitHub suffixes each matrix leg with its
matrix value (`test (3.11)`, `test (3.13)`), so a matrix job can never satisfy
a branch-protection context named `verify` — protection would wait forever for
a check that cannot arrive. The aggregator fails if any leg failed, was
skipped, or was cancelled.

`verify` is a required status check on `main` with `enforce_admins` enabled,
so nothing reaches `main` without it passing.

Reproduce CI locally with the same tool versions it pins:

```bash
pip install "ruff==0.17.0" "mypy==2.4.0" build
ruff check src tests scripts && ruff format --check src tests scripts
mypy src && pytest -q
```

Run the test suite and read `tests/test_triage_desk_adapter.py` for a worked
example of converting a real triage-desk log and grading it — the CLI
currently only accepts the canonical schema directly, so raw triage-desk logs
go through `scripts/to_canonical.py` first; a convenience flag on the CLI
itself is listed in ROADMAP.md as not-yet-done.

## What's honest and what isn't here yet

- The rubric rules below are implemented and unit-tested against synthetic
  trajectories built specifically to trigger (or not trigger) each rule.
  That's a real, if small, test of the rule logic.
- The triage-desk example is a **real** recorded run (copied from that
  repo's own `triage-logs/last-run.json`), run through the grader for real,
  and now the one trajectory with a hand-written human label. That label
  caught a real false positive in the rubric (see above) — which is also a
  reminder that one labeled trajectory cannot validate the rubric generally.
- There is no LLM-judge integration yet. The current rubric rules are
  deterministic checks (rule-based, not model-graded) — simpler, but also
  more limited, than the LLM-judge-plus-calibration design described in the
  original pitch. That's the next real increment, not something faked here.
- The gold set has **1** label against a target of 20–30, every verdict in it
  is `ok`, and there is only one labeler. So: no rule has yet been shown able
  to discriminate on real data, kappa is undefined everywhere, and systematic
  bias in the labels is invisible. All four limitations are restated in
  `CALIBRATION.md` next to the number itself.

## License

MIT
