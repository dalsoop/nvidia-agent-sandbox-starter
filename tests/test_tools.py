import json
from pathlib import Path

import pytest

from agent.skills import load_skills
from agent.tools import Toolbox, ToolError, Workspace

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    root = tmp_path / "ws"
    root.mkdir()
    return Workspace(root)


def test_nested_write_and_read_stay_inside(workspace: Workspace):
    workspace.write_file("notes/a.txt", "hello")
    assert (workspace.root / "notes" / "a.txt").read_text() == "hello"
    assert workspace.read_file("notes/a.txt") == "hello"


@pytest.mark.parametrize("path", ["../escape.txt", "/etc/passwd", "notes/../../escape.txt"])
def test_paths_outside_workspace_are_refused(workspace: Workspace, path: str):
    with pytest.raises(ToolError, match="escapes the workspace"):
        workspace.write_file(path, "x")


def test_sibling_directory_with_shared_prefix_is_refused(workspace: Workspace):
    # "/tmp/.../ws-evil" starts with "/tmp/.../ws" as a string; a prefix check would allow it.
    sibling = workspace.root.parent / f"{workspace.root.name}-evil"
    sibling.mkdir()
    with pytest.raises(ToolError, match="escapes the workspace"):
        workspace.write_file(f"../{sibling.name}/pwned.txt", "x")
    assert not (sibling / "pwned.txt").exists()


def test_symlink_pointing_outside_is_refused(workspace: Workspace, tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace.root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ToolError, match="escapes the workspace"):
        workspace.write_file("link/pwned.txt", "x")
    assert not (outside / "pwned.txt").exists()


def test_toolbox_returns_errors_to_the_model_instead_of_raising(workspace: Workspace):
    toolbox = Toolbox(workspace, {})
    assert toolbox.call("write_file", json.dumps({"path": "../x", "content": "y"})) == (
        "error: path escapes the workspace: ../x",
        False,
    )
    assert toolbox.call("rm_rf", "{}") == ("error: unknown tool: rm_rf", False)
    assert toolbox.call("read_file", "not json")[1] is False
    assert toolbox.call("read_file", json.dumps({"path": "a", "extra": 1})) == ("error: wrong arguments for read_file", False)


def test_load_skill_returns_the_bundled_instructions(workspace: Workspace):
    skills = load_skills(REPO / "skills")
    toolbox = Toolbox(workspace, skills)
    output, ok = toolbox.call("load_skill", json.dumps({"name": "workspace-report"}))
    assert ok and "report.md" in output
    assert toolbox.call("load_skill", json.dumps({"name": "nope"}))[1] is False
