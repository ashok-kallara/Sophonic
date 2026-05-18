"""Skill loader — discovers SKILL.md files and exposes them to the LLM."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter
from jinja2 import Environment, StrictUndefined


@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str
    tools: list[str]
    body: str


def _bundled_skills_dir() -> Path:
    return Path(__file__).parent / "skills"


def _user_skills_dir() -> Path:
    return Path.home() / ".sophonic" / "skills"


def load_skill(name: str) -> SkillMeta | None:
    """Load a single skill by name. User override dir takes precedence."""
    for base in [_user_skills_dir(), _bundled_skills_dir()]:
        skill_file = base / name / "SKILL.md"
        if skill_file.exists():
            post = frontmatter.load(skill_file)
            return SkillMeta(
                name=post.get("name", name),
                description=post.get("description", ""),
                tools=list(post.get("tools", [])),
                body=post.content,
            )
    return None


def discover() -> list[SkillMeta]:
    """Return all available skills. User skills override bundled skills of the same name."""
    seen: dict[str, SkillMeta] = {}
    for base in [_bundled_skills_dir(), _user_skills_dir()]:
        if not base.exists():
            continue
        for skill_dir in sorted(base.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            post = frontmatter.load(skill_file)
            skill_name = post.get("name", skill_dir.name)
            seen[skill_name] = SkillMeta(
                name=skill_name,
                description=post.get("description", ""),
                tools=list(post.get("tools", [])),
                body=post.content,
            )
    return list(seen.values())


def index() -> str:
    """Build the always-on skill index (name + description only, no bodies)."""
    all_skills = discover()
    if not all_skills:
        return ""
    lines = ["Available capabilities (call skill_load(name) for full instructions):"]
    for s in all_skills:
        lines.append(f"- **{s.name}**: {s.description}")
    return "\n".join(lines)


def skill_load(name: str) -> dict[str, Any]:
    """Load and return the full instructions for a named capability skill."""
    all_skills = discover()
    meta = next((s for s in all_skills if s.name == name), None)
    if meta is None:
        available = [s.name for s in all_skills]
        return {"error": f"Unknown skill: {name!r}. Available: {available}"}
    return {"name": meta.name, "body": meta.body}


def template(skill_name: str, template_name: str, **kwargs: Any) -> str:
    """Render a Jinja2 template from a skill's templates/ directory."""
    for base in [_user_skills_dir(), _bundled_skills_dir()]:
        tpl_path = base / skill_name / "templates" / f"{template_name}.md.j2"
        if tpl_path.exists():
            env = Environment(undefined=StrictUndefined)
            return env.from_string(tpl_path.read_text(encoding="utf-8")).render(**kwargs)
    raise FileNotFoundError(f"Template not found: {skill_name}/templates/{template_name}.md.j2")


def validate(registry: dict[str, Any]) -> None:
    """Raise ValueError if a partially-registered skill has missing tools.

    Skills with zero registered tools are silently skipped (feature disabled).
    """
    for skill in discover():
        registered = [t for t in skill.tools if t in registry]
        missing = [t for t in skill.tools if t not in registry]
        if registered and missing:
            raise ValueError(
                f"Skill '{skill.name}' has partially registered tools. "
                f"Missing from registry: {missing}"
            )
