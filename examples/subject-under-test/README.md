# Example: a real triage-desk trajectory

`triage-desk-run-issue24.json` is copied verbatim from
`edgeorgie/triage-desk`'s own `triage-logs/last-run.json` /
`triage-logs/runs.jsonl` (issue #24, heuristic fallback mode, no LLM key
configured in that run). It is included here read-only, as a real worked
example of the adapter + grader running against an actual agent log — not
as a benchmark of triage-desk's quality.

```bash
pytest tests/test_triage_desk_adapter.py -v
```

Note the log's own raw shape (triage-desk's `name`/`input` fields, not this
project's `tool`/`args`) — `trajectory_grader.adapters.triage_desk` converts
it to the canonical schema before grading; see that test file for the real,
tested conversion + grading path. A convenience CLI flag for raw
triage-desk logs is listed in ROADMAP.md as future work, not implemented
today.
