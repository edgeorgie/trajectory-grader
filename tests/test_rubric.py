from trajectory_grader.rubric import (
    bad_retry_no_change,
    no_terminal_action,
    redundant_call_after_success,
    wrong_tool_before_right,
)
from trajectory_grader.schema import Step, Trajectory


def _traj(steps):
    return Trajectory(task_id="t", agent_name="a", steps=tuple(steps))


def test_wrong_tool_before_right_flags_the_detour():
    check = wrong_tool_before_right(wrong_tool="guess_tool", right_tool="search_tool")
    traj = _traj(
        [
            Step(kind="tool", tool="guess_tool", args={}, ok=True),
            Step(kind="tool", tool="search_tool", args={}, ok=True),
        ]
    )
    violations = check(traj)
    assert len(violations) == 1
    assert violations[0].rule == "wrong_tool_before_right"
    assert violations[0].step_index == 0


def test_wrong_tool_before_right_is_silent_when_right_tool_never_used():
    # if the right tool was never demonstrated as reachable, don't assume
    # the wrong tool was actually wrong for this task
    check = wrong_tool_before_right(wrong_tool="guess_tool", right_tool="search_tool")
    traj = _traj([Step(kind="tool", tool="guess_tool", args={}, ok=True)])
    assert check(traj) == []


def test_wrong_tool_before_right_is_silent_when_right_tool_called_first():
    check = wrong_tool_before_right(wrong_tool="guess_tool", right_tool="search_tool")
    traj = _traj(
        [
            Step(kind="tool", tool="search_tool", args={}, ok=True),
            Step(kind="tool", tool="guess_tool", args={}, ok=True),
        ]
    )
    assert check(traj) == []


def test_bad_retry_no_change_flags_identical_retry_after_failure():
    traj = _traj(
        [
            Step(kind="tool", tool="fetch", args={"id": 1}, ok=False),
            Step(kind="tool", tool="fetch", args={"id": 1}, ok=True),
        ]
    )
    violations = bad_retry_no_change(traj)
    assert len(violations) == 1
    assert violations[0].step_index == 1


def test_bad_retry_no_change_allows_a_retry_that_adapts():
    traj = _traj(
        [
            Step(kind="tool", tool="fetch", args={"id": 1}, ok=False),
            Step(kind="tool", tool="fetch", args={"id": 2}, ok=True),
        ]
    )
    assert bad_retry_no_change(traj) == []


def test_redundant_call_after_success_flags_a_repeat():
    traj = _traj(
        [
            Step(kind="tool", tool="submit", args={"x": 1}, ok=True),
            Step(kind="tool", tool="submit", args={"x": 1}, ok=True),
        ]
    )
    violations = redundant_call_after_success(traj)
    assert len(violations) == 1
    assert violations[0].step_index == 1


def test_redundant_call_after_success_allows_distinct_calls():
    traj = _traj(
        [
            Step(kind="tool", tool="submit", args={"x": 1}, ok=True),
            Step(kind="tool", tool="submit", args={"x": 2}, ok=True),
        ]
    )
    assert redundant_call_after_success(traj) == []


def test_no_terminal_action_flags_a_trajectory_that_never_acts():
    check = no_terminal_action(terminal_tools=frozenset({"submit"}))
    traj = _traj([Step(kind="tool", tool="search", args={}, ok=True)])
    violations = check(traj)
    assert len(violations) == 1
    assert violations[0].rule == "no_terminal_action"


def test_no_terminal_action_passes_when_a_terminal_tool_is_called():
    check = no_terminal_action(terminal_tools=frozenset({"submit"}))
    traj = _traj(
        [
            Step(kind="tool", tool="search", args={}, ok=True),
            Step(kind="tool", tool="submit", args={}, ok=True),
        ]
    )
    assert check(traj) == []
