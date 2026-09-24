"""Load Agent Skills (SKILL.md with name/description frontmatter).

The agent sees only each skill's name and description up front and reads the
full instructions on demand through the ``load_skill`` tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024


class SkillError(ValueError):
    """A SKILL.md file does not follow the expected format."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: Path


def parse_skill(text: str, path: Path) -> Skill:
    if not text.startswith("---\n"):
        raise SkillError(f"{path}: missing frontmatter")
    try:
        header, body = text[4:].split("\n---\n", 1)
    except ValueError:
        raise SkillError(f"{path}: unterminated frontmatter") from None
    meta: dict[str, str] = {}
    for line in header.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise SkillError(f"{path}: invalid frontmatter line {line!r}")
        meta[key.strip()] = value.strip().strip("\"'")
    name = meta.get("name", "")
    description = meta.get("description", "")
    if not NAME_PATTERN.match(name) or len(name) > MAX_NAME:
        raise SkillError(f"{path}: name must be lowercase letters, digits and hyphens (max {MAX_NAME})")
    if path.parent.name != name:
        raise SkillError(f"{path}: name {name!r} must match its directory {path.parent.name!r}")
    if not description or len(description) > MAX_DESCRIPTION:
        raise SkillError(f"{path}: description is required (max {MAX_DESCRIPTION} characters)")
    return Skill(name=name, description=description, body=body.strip(), path=path)


def load_skills(root: Path) -> dict[str, Skill]:
    if not root.is_dir():
        return {}
    skills = {}
    for skill_file in sorted(root.glob("*/SKILL.md")):
        skill = parse_skill(skill_file.read_text(encoding="utf-8"), skill_file)
        skills[skill.name] = skill
    return skills


def catalog(skills: dict[str, Skill]) -> str:
    if not skills:
        return "No skills are installed."
    lines = ["Available skills (call load_skill with the name before following one):"]
    lines += [f"- {skill.name}: {skill.description}" for skill in skills.values()]
    return "\n".join(lines)
