from importlib import resources
from pathlib import Path

SKILL_NAME = "dev-sandbox"
TARGETS = {
    "claude": Path(".claude") / "skills" / SKILL_NAME,
    "pi": Path(".pi") / "agent" / "skills" / SKILL_NAME,
}


def expand_targets(names: list) -> list:
    if not names or "all" in names:
        return list(TARGETS)
    unknown = [n for n in names if n not in TARGETS]
    if unknown:
        raise ValueError(f"未知的工具：{', '.join(unknown)}，可选：{', '.join(TARGETS)}")
    return names


def install_skills(names: list, home: Path | None = None) -> list:
    home = home or Path.home()
    content = resources.files("dev_sandbox").joinpath("skill/SKILL.md").read_text(encoding="utf-8")
    written = []
    for name in expand_targets(names):
        dest = home / TARGETS[name]
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "SKILL.md").write_text(content, encoding="utf-8")
        written.append(dest / "SKILL.md")
    return written
