from trajectory_grader.grader import grade
from trajectory_grader.rubric import no_terminal_action, redundant_call_after_success
from trajectory_grader.schema import Step, Trajectory


def test_grade_collects_violations_from_every_rule():
    traj = Trajectory(
        task_id="t",
        agent_name="a",
        steps=(
            Step(kind="tool", tool="submit", args={"x": 1}, ok=True),
            Step(kind="tool", tool="submit", args={"x": 1}, ok=True),
        ),
    )
    rules = [redundant_call_after_success, no_terminal_action(terminal_tools=frozenset({"submit"}))]
    report = grade(traj, rules)
    assert report.num_tool_calls == 2
    assert not report.passed
    assert len(report.violations) == 1
    assert report.violations[0].rule == "redundant_call_after_success"


def test_grade_passes_clean_trajectory():
    traj = Trajectory(
        task_id="t2",
        agent_name="a",
        steps=(Step(kind="tool", tool="submit", args={"x": 1}, ok=True),),
    )
    report = grade(traj, [no_terminal_action(terminal_tools=frozenset({"submit"}))])
    assert report.passed
    assert "no rubric violations" in report.summary()
