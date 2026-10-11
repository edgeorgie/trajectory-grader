"""Tests for the CLI's exit-code contract and its argument surface.

These exist because the CLI is the only interface that a CI gate or another
script would actually call, and its documented exit codes (0 clean / 1
violations / 2 usage-or-input error) are part of that contract. A crash with
a raw traceback — which is what `--help` used to produce — is not a usable
exit code, so the help path is asserted too.
"""

import json

import pytest

from trajectory_grader.cli import EXIT_OK, EXIT_USAGE, EXIT_VIOLATIONS, main

CLEAN = {
    "task_id": "clean-1",
    "agent_name": "unit-test-agent",
    "steps": [
        {"kind": "thought", "text": "pick the right tool first"},
        {"kind": "tool", "tool": "find_similar", "args": {"q": "x"}, "ok": True},
        {"kind": "tool", "tool": "submit_triage", "args": {"label": "bug"}, "ok": True},
    ],
}

# Same terminal call twice with identical args -> redundant_call_after_success.
VIOLATING = {
    "task_id": "dirty-1",
    "agent_name": "unit-test-agent",
    "steps": [
        {"kind": "tool", "tool": "submit_triage", "args": {"label": "bug"}, "ok": True},
        {"kind": "tool", "tool": "submit_triage", "args": {"label": "bug"}, "ok": True},
    ],
}


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_clean_trajectory_exits_zero(tmp_path, capsys):
    path = _write(tmp_path, "clean.json", CLEAN)
    assert main(["prog", path]) == EXIT_OK
    assert "no rubric violations" in capsys.readouterr().out


def test_violating_trajectory_exits_one_and_names_the_rule(tmp_path, capsys):
    path = _write(tmp_path, "dirty.json", VIOLATING)
    assert main(["prog", path]) == EXIT_VIOLATIONS
    assert "redundant_call_after_success" in capsys.readouterr().out


def test_missing_file_exits_usage_without_traceback(tmp_path, capsys):
    assert main(["prog", str(tmp_path / "nope.json")]) == EXIT_USAGE
    assert "cannot read" in capsys.readouterr().err


def test_malformed_json_exits_usage(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert main(["prog", str(path)]) == EXIT_USAGE
    assert "not valid JSON" in capsys.readouterr().err


def test_valid_json_but_wrong_shape_exits_usage(tmp_path, capsys):
    path = _write(tmp_path, "shape.json", {"task_id": "t"})  # no steps/agent_name
    assert main(["prog", str(path)]) == EXIT_USAGE
    assert "not a valid canonical trajectory" in capsys.readouterr().err


def test_no_arguments_exits_usage(capsys):
    assert main(["prog"]) == EXIT_USAGE
    assert "TRAJECTORY.json" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_exits_zero_and_prints_usage(flag, capsys):
    """Regression guard: `--help` previously raised FileNotFoundError.

    The old CLI read argv[1] as a path unconditionally, so the standard help
    flag crashed with a traceback instead of printing usage.
    """
    assert main(["prog", flag]) == EXIT_OK
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "TRAJECTORY.json" in out
    # argparse hard-wraps the description, so assert on unwrapped fragments only.
    assert "Exit status: 0 = no violations" in out
