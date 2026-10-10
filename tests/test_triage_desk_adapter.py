import json
from pathlib import Path

from trajectory_grader.adapters.triage_desk import trajectory_from_triage_desk_log
from trajectory_grader.grader import grade
from trajectory_grader.rubric import redundant_call_after_success

EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "subject-under-test"
    / "triage-desk-run-issue24.json"
)


def test_adapter_converts_real_triage_desk_log_shape():
    entry = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    traj = trajectory_from_triage_desk_log(entry)
    assert traj.task_id == "triage-desk-issue-24"
    assert traj.agent_name == "edgeorgie/triage-desk"
    assert traj.final_action == "bug"
    tool_names = [s.tool for s in traj.tool_steps()]
    assert tool_names == ["submit_triage", "submit_triage"]


def test_real_triage_desk_run_trips_the_redundant_call_rule():
    # This is a real, known property of this specific captured run (it
    # really does call submit_triage twice with identical args) — not a
    # synthetic fixture. It demonstrates the grader finding a genuine
    # process-quality smell in a real log, without claiming anything
    # about triage-desk's overall quality.
    entry = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    traj = trajectory_from_triage_desk_log(entry)
    report = grade(traj, [redundant_call_after_success])
    assert not report.passed
    assert report.violations[0].rule == "redundant_call_after_success"
