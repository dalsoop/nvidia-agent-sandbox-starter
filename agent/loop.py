"""The agent loop: ask the model, run the tool calls it makes, repeat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from agent.skills import Skill, catalog
from agent.tools import Toolbox

SYSTEM_PROMPT = """You are a careful agent working in a sandboxed workspace.
Act only through the provided tools. File paths are relative to the workspace root.
If an installed skill matches the task, call load_skill first and follow its instructions.
Never invent file contents you have not read.
When the task is done, reply with a short final answer and no tool calls."""


class Model(Protocol):
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]: ...


@dataclass
class RunResult:
    status: str
    answer: str
    steps: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def run(task: str, model: Model, toolbox: Toolbox, skills: dict[str, Skill], max_steps: int = 8) -> RunResult:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{catalog(skills)}"},
        {"role": "user", "content": task},
    ]
    log: list[dict[str, Any]] = []

    for step in range(1, max_steps + 1):
        reply = model.complete(messages, toolbox.specs)
        calls = reply.get("tool_calls") or []
        content = (reply.get("content") or "").strip()

        assistant: dict[str, Any] = {"role": "assistant", "content": content}
        if calls:
            assistant["tool_calls"] = calls
        messages.append(assistant)

        if not calls:
            if not content:
                return RunResult("empty_answer", "", step, log)
            return RunResult("success", content, step, log)

        for call in calls:
            function = call.get("function") or {}
            name = function.get("name", "")
            arguments = function.get("arguments") or "{}"
            output, ok = toolbox.call(name, arguments)
            log.append({"step": step, "tool": name, "arguments": arguments[:200], "ok": ok})
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": output})

    return RunResult("max_steps", "", max_steps, log)
