import re
from pathlib import Path

NICHE_NAMES = {"thoi-trang": "Thời trang", "my-pham": "Mỹ phẩm", "do-an": "Đồ ăn",
               "phu-kien": "Phụ kiện", "chung": "Khác (chung)"}


def niche_section(niche: str, agent_dir: Path) -> str:
    text = (agent_dir / ".claude" / "skills" / "niche-hooks" / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(niche)}\s*\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    if not m:
        raise KeyError(niche)
    return m.group(1).strip()


def _body(name: str, agent_dir: Path) -> str:
    text = (agent_dir / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    return re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S).strip()


def skill_body(name: str, agent_dir: Path) -> str:
    """SKILL.md without its frontmatter."""
    return _body(name, agent_dir)


def niche_intro(agent_dir: Path) -> str:
    """The paragraph of niche-hooks/SKILL.md that comes before the first niche section."""
    return re.split(r"^## ", _body("niche-hooks", agent_dir), maxsplit=1, flags=re.M)[0].strip()
