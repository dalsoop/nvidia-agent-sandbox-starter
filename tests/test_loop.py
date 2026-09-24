import json
from pathlib import Path

from agent.llm import ChatClient, Endpoint
from agent.loop import run
from agent.skills import load_skills
from agent.tools import Toolbox, Workspace
from tests.conftest import final, tool_call

REPO = Path(__file__).resolve().parent.parent


def _setup(fake_llm, tmp_path: Path):
    skills = load_skills(REPO / "skills")
    toolbox = Toolbox(Workspace(tmp_path), skills)
    client = ChatClient(Endpoint(fake_llm.base_url, None), "m")
    return client, toolbox, skills


def test_tool_calls_are_executed_and_results_fed_back(fake_llm, tmp_path: Path):
    fake_llm.reply(tool_call("load_skill", {"name": "workspace-report"}, "c1"))
    fake_llm.reply(tool_call("write_file", {"path": "report.md", "content": "## Files\n"}, "c2"))
    fake_llm.reply(final("Wrote report.md"))
    client, toolbox, skills = _setup(fake_llm, tmp_path)

    result = run("inventory the workspace", client, toolbox, skills)

    assert (result.status, result.answer, result.steps) == ("success", "Wrote report.md", 3)
    assert (tmp_path / "report.md").read_text() == "## Files\n"
    assert [c["tool"] for c in result.tool_calls] == ["load_skill", "write_file"]
    # The model saw the skill catalog, the skill body, and the write confirmation.
    system_prompt = fake_llm.requests[0]["body"]["messages"][0]["content"]
    assert "workspace-report" in system_prompt
    second_turn = fake_llm.requests[1]["body"]["messages"]
    assert second_turn[-1]["role"] == "tool" and "report.md" in second_turn[-1]["content"]
    assert fake_llm.requests[2]["body"]["messages"][-1]["content"].startswith("wrote ")


def test_refused_tool_call_is_reported_to_the_model(fake_llm, tmp_path: Path):
    fake_llm.reply(tool_call("write_file", {"path": "../escape.txt", "content": "x"}))
    fake_llm.reply(final("Could not write outside the workspace."))
    client, toolbox, skills = _setup(fake_llm, tmp_path)

    result = run("try to escape", client, toolbox, skills)

    assert result.status == "success"
    assert result.tool_calls[0]["ok"] is False
    assert "escapes the workspace" in fake_llm.requests[1]["body"]["messages"][-1]["content"]
    assert not (tmp_path.parent / "escape.txt").exists()


def test_step_limit_stops_the_loop(fake_llm, tmp_path: Path):
    for index in range(3):
        fake_llm.reply(tool_call("list_files", {"path": "."}, f"c{index}"))
    client, toolbox, skills = _setup(fake_llm, tmp_path)
    result = run("loop forever", client, toolbox, skills, max_steps=2)
    assert (result.status, result.steps) == ("max_steps", 2)


def test_empty_answer_is_not_success(fake_llm, tmp_path: Path):
    fake_llm.reply({"role": "assistant", "content": None})
    client, toolbox, skills = _setup(fake_llm, tmp_path)
    assert run("say nothing", client, toolbox, skills).status == "empty_answer"


def test_tools_are_advertised_on_every_request(fake_llm, tmp_path: Path):
    fake_llm.reply(final("hi"))
    client, toolbox, skills = _setup(fake_llm, tmp_path)
    run("hello", client, toolbox, skills)
    names = [t["function"]["name"] for t in fake_llm.requests[0]["body"]["tools"]]
    assert names == ["list_files", "read_file", "write_file", "load_skill"]
    assert json.loads(json.dumps(fake_llm.requests[0]["body"]))["tool_choice"] == "auto"
