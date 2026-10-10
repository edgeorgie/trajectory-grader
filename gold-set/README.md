# Gold set — empty on day 1

This directory is where hand-labeled trajectories will go: real recorded
agent runs, each labeled by a human (not generated or auto-labeled) with a
process-quality verdict per rubric rule, plus a short note on *why*.

Once there are labels here, the plan is:

1. Run the (future) LLM-judge over the same trajectories.
2. Compare judge output to the human labels per rule.
3. Report the raw agreement rate / disagreement cases plainly in a
   `CALIBRATION.md`, including the unflattering ones — this is the part of
   the pitch that actually matters, per the project's own honesty
   requirement.

Nothing here yet because nothing has been labeled yet. Do not reference a
calibration number until `CALIBRATION.md` exists with real data behind it.
