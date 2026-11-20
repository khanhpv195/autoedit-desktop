import pytest
from autoedit.agent.library import niche_section, NICHE_NAMES
from autoedit.project import NICHES
from autoedit.resources import agent_dir


@pytest.mark.parametrize("niche", NICHES)
def test_every_niche_has_section_with_10_hooks(niche):
    sec = niche_section(niche, agent_dir())
    assert sec.startswith("Order:")
    assert sum(1 for l in sec.splitlines() if l.startswith('- "')) == 10


def test_unknown_niche():
    with pytest.raises(KeyError):
        niche_section("xe-hoi", agent_dir())


def test_names_cover_niches():
    assert set(NICHE_NAMES) == set(NICHES)


def test_skill_frontmatter_names_match_dirs():
    for d in (agent_dir() / ".claude" / "skills").iterdir():
        head = (d / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        assert f"name: {d.name}" in head
