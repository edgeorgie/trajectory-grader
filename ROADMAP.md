# Roadmap (honest, not aspirational)

This file exists so future sessions (and anyone reviewing this repo) can see
what day 1 deliberately did NOT attempt, and why. The project idea
(`PORTFOLIO-EXPANSION-IDEAS.md`, rank #2) specifically calls for judge
calibration against a hand-labeled gold set — that is real, non-trivial work
and is not done yet.

## Done on day 1

- Canonical `Trajectory` / `Step` schema with a JSON loader and round-trip
  tests.
- A declarative rubric format (a plain list of named rule objects) and four
  rule implementations: wrong-tool-before-right, bad-retry-no-change,
  redundant-call-after-success, no-terminal-action.
- A grader that runs a rubric against a trajectory and returns a structured
  report (per-rule pass/fail + a short explanation per violation).
- An adapter that converts triage-desk's real run-log JSON into the
  canonical schema, exercised against one real captured run.
- A real test suite, run locally, all passing (see commit message / CI for
  the exact count — do not copy a stale number from here).

## Explicitly NOT done yet (future, spaced-out sessions)

- **LLM-judge scoring.** Current rules are deterministic/rule-based. An
  LLM-judge pass (with its own prompt, its own failure modes, and its own
  cost) is a separate, larger piece of work.
- **A gold set large enough to mean anything.** The calibration machinery is
  built and runs (`labels.py`, `agreement.py`,
  `python -m trajectory_grader.calibrate`, `CALIBRATION.md`), with per-rule
  raw agreement and Cohen's kappa, and **1** trajectory labeled by hand.
  The target is 20-30. At n=1 kappa is undefined on every rule and the
  reported raw agreement means almost nothing — `CALIBRATION.md` states this
  rather than publishing the flattering 1.000.
- **Gold-set cases where a rule should actually fire.** Every verdict labeled
  so far is `ok`, so nothing yet distinguishes a working rule from one that
  never fires. This is the single most valuable next addition, ahead of more
  labels in general. **Four real unlabeled trajectories are now committed for
  exactly this** (`examples/subject-under-test/budget-keeper/`), three of
  which are halt/refusal cases a rule genuinely fires on. Writing their
  verdicts is a human step by design — this repo infers no labels.
- **Inter-rater agreement.** Current numbers are human-vs-rubric with a single
  labeler. Two independent humans labeling the same trajectories would reveal
  systematic bias in the labels, which is currently invisible.
- **More rubric cases.** The four rules above are a starting set chosen to
  be clearly testable, not an exhaustive process-quality taxonomy. "Asked a
  clarifying question instead of guessing" in particular isn't implemented
  yet — neither subject's trajectories currently exercise that path, so
  there is nothing real to test it against.
- **A third subject under test.** Two are now graded (triage-desk's step-list
  loop and budget-keeper's governor event stream), which was enough to find
  a false positive neither could have surfaced alone. A third with a
  different failure mode — one that actually retries, or genuinely picks the
  wrong tool first — would exercise the two rules that still have no real
  positive case.

## Why this is spread across multiple days

This portfolio's existing adversarial critique flagged a prior "burst build"
pattern (6 repos in 3 days) as a credibility red flag. This repo's first
commit is intentionally scoped to a working, tested slice — not the whole
pitch — and later commits (bug fixes, more rules, the gold set, the judge)
are expected to land on separate, ordinary days, not in one sitting.
