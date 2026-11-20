import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from autoedit.errors import BadInput
from autoedit.fsutil import atomic_write_text

NICHES = ("thoi-trang", "my-pham", "do-an", "phu-kien", "chung")
_FIELDS = ("niche", "clip", "logo", "music", "prompt", "script_card", "runs", "posts")


@dataclass
class Project:
    dir: Path
    niche: str
    clip: str
    logo: str | None = None
    music: str | None = None
    prompt: str = ""
    script_card: dict | None = None
    runs: list[dict] = field(default_factory=list)
    posts: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, dir: Path) -> "Project":
        dir = Path(dir)
        f = dir / "project.json"
        if not f.exists():
            raise BadInput(f"Không thấy {f}")
        data = json.loads(f.read_text(encoding="utf-8"))
        p = cls(dir=dir, **{k: data[k] for k in _FIELDS if k in data})
        if p.niche not in NICHES:
            raise BadInput(f"Ngành không hợp lệ: {p.niche}")
        if not p.clip_path.exists():
            raise BadInput("Không thấy file clip trong project")
        p.work_dir.mkdir(parents=True, exist_ok=True)
        return p

    def save(self) -> None:
        data = {k: v for k, v in asdict(self).items() if k in _FIELDS}
        atomic_write_text(self.dir / "project.json", json.dumps(data, ensure_ascii=False, indent=2))

    @property
    def input_dir(self) -> Path:
        return self.dir / "input"

    @property
    def work_dir(self) -> Path:
        return self.dir / "work"

    @property
    def clip_path(self) -> Path:
        return self.input_dir / self.clip

    @property
    def logo_path(self) -> Path | None:
        return self.input_dir / self.logo if self.logo else None

    @property
    def music_path(self) -> Path | None:
        return self.input_dir / self.music if self.music else None

    def new_run_dir(self) -> Path:
        runs = self.dir / "runs"
        runs.mkdir(exist_ok=True)
        n = 1 + max((int(p.name) for p in runs.iterdir() if p.name.isdigit()), default=0)
        d = runs / str(n)
        d.mkdir()
        return d
