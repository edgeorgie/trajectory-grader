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

This is deliberately narrow in scope for day 1: a canonical trajectory
format, a small rule engine, and a handful of rubric checks with real unit
tests. It is **not** yet: an LLM-judge, calibrated against a hand-labeled
gold set, or validated against any large trajectory corpus. See
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
  adapters/
    triage_desk.py   converts edgeorgie/triage-desk's run-log JSON format
                      into the canonical Trajectory schema
scripts/
  to_canonical.py   adapter CLI: raw triage-desk log -> canonical JSON on
                    stdout. Committed (rather than inlined in the workflow)
                    so the exact command CI runs is runnable locally.
tests/           unit tests for schema, rubric rules, the grader, and the
                 CLI's exit-code contract
examples/
  subject-under-test/   a real triage-desk run log, used as a worked example
gold-set/        EMPTY for now — see ROADMAP.md. This is where hand-labeled
                 trajectories + judge-vs-human agreement will go once built.
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

On the committed example this currently exits `1` and reports one real
`redundant_call_after_success` violation — that is the grader's opinion of
one real trajectory, not a validated measurement of the subject's quality
(see "What's honest and what isn't here yet" below).

## Continuous integration

Every push and pull request to `main` runs the `verify` workflow
(`.github/workflows/verify.yml`) on Python 3.11 and 3.13:

- `ruff check` (lint) and `ruff format --check` (formatting)
- `mypy --strict` over `src/`
- the full `pytest` suite
- the CLI contract: `--help` exits `0`, and the real example trajectory
  above is graded without crashing
- a wheel build, then an import of that wheel from a clean virtualenv

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
  repo's own `triage-logs/last-run.json`), run through the grader for real.
  Its score is reported as "the grader's opinion of one real trajectory",
  not as a validated measurement of triage-desk's quality — there is no
  human-labeled ground truth for this specific trajectory yet.
- There is no LLM-judge integration yet. The current rubric rules are
  deterministic checks (rule-based, not model-graded) — simpler, but also
  more limited, than the LLM-judge-plus-calibration design described in the
  original pitch. That's the next real increment, not something faked here.
- There is no gold set yet. `gold-set/` exists as a placeholder with a
  README explaining what needs to go there and why it isn't there on day 1.

## License

MIT
