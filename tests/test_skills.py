from pathlib import Path

import pytest

from agent.skills import SkillError, catalog, load_skills, parse_skill

REPO = Path(__file__).resolve().parent.parent


def test_bundled_skills_are_valid():
    skills = load_skills(REPO / "skills")
    assert "workspace-report" in skills
    assert "workspace-report" in catalog(skills)


def _skill_file(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name / "SKILL.md"
    path.parent.mkdir()
    path.write_text(text)
    return path


def test_parse_reads_frontmatter_and_body(tmp_path: Path):
    path = _skill_file(tmp_path, "demo", "---\nname: demo\ndescription: \"Does a thing\"\n---\n# Body\nStep 1\n")
    skill = parse_skill(path.read_text(), path)
    assert (skill.name, skill.description, skill.body) == ("demo", "Does a thing", "# Body\nStep 1")


@pytest.mark.parametrize(
    "text",
    [
        "# no frontmatter\n",
        "---\nname: demo\n",
        "---\nname: Demo\ndescription: x\n---\nbody",
        "---\nname: demo\n---\nbody",
        "---\nname: other\ndescription: x\n---\nbody",
    ],
)
def test_invalid_skills_are_rejected(tmp_path: Path, text: str):
    path = _skill_file(tmp_path, "demo", text)
    with pytest.raises(SkillError):
        parse_skill(text, path)
