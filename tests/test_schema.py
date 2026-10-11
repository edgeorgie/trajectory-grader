import pytest

from trajectory_grader.schema import Step, Trajectory, trajectory_from_dict


def test_step_rejects_invalid_kind():
    with pytest.raises(ValueError, match="must be 'thought' or 'tool'"):
        Step(kind="banana")


def test_tool_step_requires_tool_name():
    with pytest.raises(ValueError, match="must have a tool name"):
        Step(kind="tool")


def test_trajectory_from_dict_round_trips():
    data = {
        "task_id": "t1",
        "agent_name": "demo-agent",
        "final_action": "submit",
        "steps": [
            {"kind": "thought", "text": "thinking"},
            {
                "kind": "tool",
                "tool": "search",
                "args": {"q": "x"},
                "result": "ok",
                "ok": True,
            },
        ],
    }
    traj = trajectory_from_dict(data)
    assert traj.task_id == "t1"
    assert traj.agent_name == "demo-agent"
    assert len(traj.steps) == 2
    assert traj.steps[0].kind == "thought"
    assert traj.steps[1].tool == "search"
    assert len(traj.tool_steps()) == 1


def test_tool_steps_filters_out_thoughts():
    traj = Trajectory(
        task_id="t2",
        agent_name="a",
        steps=(
            Step(kind="thought", text="hmm"),
            Step(kind="tool", tool="x", args={}),
            Step(kind="thought", text="hmm again"),
            Step(kind="tool", tool="y", args={}),
        ),
    )
    assert [s.tool for s in traj.tool_steps()] == ["x", "y"]
