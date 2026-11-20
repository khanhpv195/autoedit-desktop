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
