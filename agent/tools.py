"""Tools exposed to the model: workspace-scoped file access and skill loading.

Path checks here are defense in depth. Inside OpenShell the real boundary is
Landlock plus the sandbox policy; outside a sandbox these checks are the only
thing between the model and your filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.skills import Skill

MAX_READ_BYTES = 64 * 1024
MAX_WRITE_BYTES = 256 * 1024
MAX_LIST_ENTRIES = 200


class ToolError(Exception):
    """A tool call was refused or failed; the message is shown to the model."""


class Workspace:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def resolve(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or "\x00" in relative:
            raise ToolError("path must be a non-empty string")
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root):
            raise ToolError(f"path escapes the workspace: {relative}")
        return target

    def list_files(self, path: str = ".") -> str:
        directory = self.resolve(path)
        if not directory.is_dir():
            raise ToolError(f"not a directory: {path}")
        entries = []
        for child in sorted(directory.iterdir())[:MAX_LIST_ENTRIES]:
            kind = "dir" if child.is_dir() else f"{child.stat().st_size} bytes"
            entries.append(f"{child.relative_to(self.root)} ({kind})")
        return "\n".join(entries) or "(empty)"

    def read_file(self, path: str) -> str:
        target = self.resolve(path)
        if not target.is_file():
            raise ToolError(f"not a file: {path}")
        data = target.read_bytes()
        if len(data) > MAX_READ_BYTES:
            raise ToolError(f"file is larger than {MAX_READ_BYTES} bytes: {path}")
        return data.decode("utf-8", "replace")

    def write_file(self, path: str, content: str) -> str:
        if not isinstance(content, str):
            raise ToolError("content must be a string")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_WRITE_BYTES:
            raise ToolError(f"content is larger than {MAX_WRITE_BYTES} bytes")
        target = self.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        return f"wrote {len(encoded)} bytes to {target.relative_to(self.root)}"


def _spec(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_PATH = {"type": "string", "description": "Path relative to the workspace root"}

TOOL_SPECS = [
    _spec("list_files", "List files in a workspace directory.", {"path": _PATH}, []),
    _spec("read_file", "Read a UTF-8 text file from the workspace.", {"path": _PATH}, ["path"]),
    _spec(
        "write_file",
        "Create or overwrite a UTF-8 text file in the workspace.",
        {"path": _PATH, "content": {"type": "string"}},
        ["path", "content"],
    ),
    _spec(
        "load_skill",
        "Read the full instructions of an installed skill.",
        {"name": {"type": "string", "description": "Skill name from the catalog"}},
        ["name"],
    ),
]


class Toolbox:
    def __init__(self, workspace: Workspace, skills: dict[str, Skill]) -> None:
        self.workspace = workspace
        self.skills = skills

    @property
    def specs(self) -> list[dict[str, Any]]:
        return TOOL_SPECS

    def call(self, name: str, arguments: str) -> tuple[str, bool]:
        """Run one tool call. Failures are returned to the model, not raised."""
        try:
            args = json.loads(arguments or "{}")
            if not isinstance(args, dict):
                raise ToolError("arguments must be a JSON object")
            return self._dispatch(name, args), True
        except json.JSONDecodeError:
            return "error: arguments are not valid JSON", False
        except ToolError as error:
            return f"error: {error}", False
        except TypeError:
            return f"error: wrong arguments for {name}", False
        except OSError as error:
            return f"error: {error.strerror or error}", False

    def _dispatch(self, name: str, args: dict[str, Any]) -> str:
        if name == "list_files":
            return self.workspace.list_files(**args)
        if name == "read_file":
            return self.workspace.read_file(**args)
        if name == "write_file":
            return self.workspace.write_file(**args)
        if name == "load_skill":
            skill = self.skills.get(args.get("name", ""))
            if skill is None:
                raise ToolError(f"unknown skill: {args.get('name')!r}")
            return skill.body
        raise ToolError(f"unknown tool: {name}")
