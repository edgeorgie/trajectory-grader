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
- **Hand-labeled gold set.** Need 20-30 real trajectories labeled by a human
  (me) independently of the rubric code, then a judge-vs-human agreement
  report that states the disagreement rate plainly, including if it's bad.
  Zero trajectories are labeled today.
- **More rubric cases.** The four rules above are a starting set chosen to
  be clearly testable, not an exhaustive process-quality taxonomy. "Asked a
  clarifying question instead of guessing" in particular isn't implemented
  yet — triage-desk's trajectories don't currently exercise that path, so
  there was nothing real to test it against today.
- **More subjects-under-test.** Only triage-desk's agent loop has been fed
  through the grader so far. A second, independently-built agent's
  trajectories would make the "process eval, not self-grading" story much
  stronger and is a good next addition.

## Why this is spread across multiple days

This portfolio's existing adversarial critique flagged a prior "burst build"
pattern (6 repos in 3 days) as a credibility red flag. This repo's first
commit is intentionally scoped to a working, tested slice — not the whole
pitch — and later commits (bug fixes, more rules, the gold set, the judge)
are expected to land on separate, ordinary days, not in one sitting.
