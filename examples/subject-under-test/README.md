# Subjects under test

Recorded runs from two independently-built agents, used here as **the things
being evaluated**. Neither is a benchmark of that agent's quality, and
neither is evidence that this grader works — the grader's own test suite is
what proves that, against synthetic trajectories built to trip specific
rules.

Two subjects rather than one is deliberate. A harness validated against a
single agent's log format is really a test of one adapter, and the second
subject immediately proved the point: it exposed a false positive in
`no_terminal_action` that one subject could never have surfaced (see
`../../CALIBRATION.md`).

| Subject | Log shape | What it exercises |
|---|---|---|
| `triage-desk-run-issue24.json` | a step list the agent assembled | the double-logged pre/post step pair |
| `budget-keeper/*.jsonl` | a governor **event stream** | pairing events into steps; runs halted by something other than the agent |

## 1. triage-desk — `triage-desk-run-issue24.json`

Copied verbatim from `edgeorgie/triage-desk`'s own
`triage-logs/last-run.json` (issue #24, heuristic fallback mode, no LLM key
configured in that run).

```bash
pytest tests/test_triage_desk_adapter.py -v
```

Note the log's own raw shape (triage-desk's `name`/`input` fields, not this
project's `tool`/`args`) — `trajectory_grader.adapters.triage_desk` converts
it to the canonical schema before grading. A convenience CLI flag for raw
triage-desk logs is listed in ROADMAP.md as future work.

## 2. budget-keeper — `budget-keeper/*.jsonl`

Captured from `edgeorgie/budget-keeper`, a cost-governed agent that drafts a
dependency patch plan under a hard USD ceiling. Its `--json` mode emits the
governor's event stream as JSONL, which is what these files are.

Each was produced by running, in a `budget-keeper` checkout:

```bash
npm run keeper -- --repo <repo> --budget <usd> --json > out.jsonl
```

| File | Command | What the governor did |
|---|---|---|
| `completed-express-budget-0.50.jsonl` | `--repo expressjs/express --budget 0.50` | 1 step planned, ran it, reached `roll-up`, `reason: completed` |
| `refused-at-step-0-express-budget-0.0008.jsonl` | `--repo expressjs/express --budget 0.0008` | priced step 0 at $0.000849 worst case against $0.0008 remaining and refused it; **nothing executed** |
| `halted-after-1-of-20-nextjs-budget-0.02.jsonl` | `--repo vercel/next.js --budget 0.02` | 20 steps planned, funded 1, refused step 1 pre-flight |
| `halted-after-2-of-20-nextjs-budget-0.60.jsonl` | `--repo vercel/next.js --budget 0.60` | 20 steps planned, funded 2, refused step 2 pre-flight |

`GITHUB_TOKEN` was set for all four (raises the GitHub API rate limit from 60
req/hr; it does not affect the trajectory). The two `vercel/next.js` runs
scanned 192 declared dependencies and found 19 exposed to a published
advisory, hence 20 planned steps — 19 write-ups plus the final `roll-up`.

### What is real here, and what is not

budget-keeper runs in **`simulated` inference mode** unless
`ANTHROPIC_API_KEY` is set, and none of these captures had one. So the token
counts and dollar figures inside these events come from its deterministic
simulator, **not** a provider bill. Those numbers are not claimed as real
spend anywhere in this repo.

The **control flow** is real either way, and it is the only thing this
harness grades: which steps the planner produced from a real dependency scan
of a real repository, which the governor funded, which it priced and refused,
and where the run stopped. A trajectory is a sequence of decisions; the
simulator does not fabricate the sequence.

### The `spend` events are kept, unfiltered

These are the complete streams as captured, not trimmed. `spend` fires once
per streamed chunk, so it dominates the line count:

| File | Total lines | `spend` lines |
|---|---|---|
| `refused-at-step-0-express-budget-0.0008.jsonl` | 4 | 0 |
| `halted-after-1-of-20-nextjs-budget-0.02.jsonl` | 38 | 30 |
| `completed-express-budget-0.50.jsonl` | 265 | 259 |
| `halted-after-2-of-20-nextjs-budget-0.60.jsonl` | 1005 | 993 |

They carry no trajectory information — the step a `spend` belongs to is
already represented by its start/end pair — and the adapter ignores them,
which `test_spend_telemetry_does_not_become_steps` pins. Keeping them means
the committed example is byte-for-byte what the governor emitted, so a
reader can re-derive the dollar figures rather than taking a filtered file on
trust. Read a capture's control flow with:

```bash
grep -v '"type":"spend"' halted-after-2-of-20-nextjs-budget-0.60.jsonl
```
