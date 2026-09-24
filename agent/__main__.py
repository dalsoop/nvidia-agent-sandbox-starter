"""Command line entry point: ``python -m agent "<task>"``.

Prints one JSON object to stdout. Exit codes:
0 success, 1 selfcheck found the process not sandboxed, 2 configuration error,
3 model call failed, 4 step limit reached, 5 model returned an empty answer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent import __version__
from agent.llm import DEFAULT_MODEL, ChatClient, ConfigError, LLMError, resolve_endpoint
from agent.loop import run
from agent.selfcheck import selfcheck
from agent.skills import SkillError, load_skills
from agent.tools import Toolbox, Workspace

EXIT_CODES = {"success": 0, "max_steps": 4, "empty_answer": 5}
DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent", description=__doc__.splitlines()[0])
    parser.add_argument("task", nargs="?", help="what the agent should do")
    parser.add_argument("--workspace", default=os.environ.get("AGENT_WORKSPACE", "."))
    parser.add_argument("--skills-dir", default=os.environ.get("AGENT_SKILLS_DIR", str(DEFAULT_SKILLS_DIR)))
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible base URL (default: auto)")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--selfcheck", action="store_true", help="report sandbox containment and exit")
    parser.add_argument("--egress-url", default="https://example.com/", help="URL the selfcheck tries to reach")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if args.selfcheck:
        report = selfcheck(args.workspace, egress_url=args.egress_url)
        _emit(report)
        return 0 if report["sandboxed"] else 1

    if not args.task:
        parser.error("a task is required unless --selfcheck is given")

    try:
        endpoint = resolve_endpoint(args.base_url)
        skills = load_skills(Path(args.skills_dir))
    except (ConfigError, SkillError) as error:
        _emit({"status": "config_error", "error": str(error)})
        return 2

    client = ChatClient(endpoint, args.model)
    toolbox = Toolbox(Workspace(args.workspace), skills)
    meta = {"requested_model": args.model, "endpoint": endpoint.mode, "skills": sorted(skills)}
    try:
        result = run(args.task, client, toolbox, skills, max_steps=args.max_steps)
    except LLMError as error:
        _emit({"status": "llm_error", "error": str(error), "served_model": client.served_model, **meta})
        return 3

    _emit(
        {
            "status": result.status,
            "answer": result.answer,
            "steps": result.steps,
            "tool_calls": result.tool_calls,
            "served_model": client.served_model,
            **meta,
        }
    )
    return EXIT_CODES[result.status]


if __name__ == "__main__":
    sys.exit(main())
