import contextlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from autoedit.errors import BadInput
from autoedit.fsutil import atomic_write_text


class LockBusy(Exception):
    pass


@contextlib.contextmanager
def file_lock(path: Path, blocking: bool = True):
    """Exclusive advisory lock on `path` (created if missing). Raises LockBusy when not blocking and held.
    fcntl.flock on POSIX, msvcrt.locking on Windows. Released when the process dies."""
    path = Path(path)
    with open(path, "a+b") as f:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            while True:
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if not blocking:
                        raise LockBusy(str(path)) from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except OSError:
                raise LockBusy(str(path)) from None
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_project_json(dir: Path) -> dict:
    f = Path(dir) / "project.json"
    if not f.exists():
        raise BadInput(f"Không thấy {f}")
    return json.loads(f.read_text(encoding="utf-8"))


def update_project(dir: Path, mutate) -> dict:
    """Lock project.json, re-read it from disk, apply `mutate(data: dict)`, write it atomically. Returns the data.
    Long operations (an edit, an upload) must not save a copy they loaded earlier: do the change here, so
    fields written meanwhile by another command (runs, posts) are kept."""
    dir = Path(dir)
    with file_lock(dir / "project.json.lock"):
        data = read_project_json(dir)
        mutate(data)
        atomic_write_text(dir / "project.json", json.dumps(data, ensure_ascii=False, indent=2))
    return data


NICHES = ("thoi-trang", "my-pham", "do-an", "phu-kien", "chung")
MAX_CLIPS, MAX_IMAGES = 10, 20
_FIELDS = ("niche", "clips", "images", "logo", "music", "prompt", "script_card", "runs", "posts",
           "voiceover", "product_info", "cta_text", "length")
DEFAULT_CTA = "BẤM GIỎ HÀNG 👇"
CTA_MAX = 30
PRODUCT_INFO_MAX = 500
LENGTHS = {"short": (15.0, 20.0), "medium": (20.0, 35.0), "long": (35.0, 60.0)}


def _sanitize(data: dict) -> None:
    """New optional keys (v0.3): bad or missing values fall back to defaults instead of failing the load."""
    if data.get("length") not in LENGTHS:
        data["length"] = "medium"
    cta = data.get("cta_text")
    cta = cta.strip() if isinstance(cta, str) else ""
    data["cta_text"] = cta if 0 < len(cta) <= CTA_MAX else DEFAULT_CTA
    info = data.get("product_info")
    data["product_info"] = info[:PRODUCT_INFO_MAX] if isinstance(info, str) else ""
    if not isinstance(data.get("voiceover"), dict):
        data["voiceover"] = None


def _check_name(name) -> None:
    """File names in project.json live directly in input/: no separators, no '..', no absolute paths."""
    if not isinstance(name, str) or name in ("", ".", "..") or Path(name).name != name or "\\" in name:
        raise BadInput(f"Tên file không hợp lệ: {name!r}")


@dataclass
class Project:
    dir: Path
    niche: str
    clips: list[str]
    images: list[str] = field(default_factory=list)
    logo: str | None = None
    music: str | None = None
    prompt: str = ""
    script_card: dict | None = None
    runs: list[dict] = field(default_factory=list)
    posts: list[dict] = field(default_factory=list)
    voiceover: dict | None = None      # {"enabled", "voice_id", "voice_name"}
    product_info: str = ""
    cta_text: str = DEFAULT_CTA
    length: str = "medium"

    @classmethod
    def load(cls, dir: Path, require_media: bool = True) -> "Project":
        """require_media: clips and images must exist on disk (commands that prepare media). Captions / publishing
        pass False: a deleted image must not break them."""
        dir = Path(dir)
        f = dir / "project.json"
        if not f.exists():
            raise BadInput(f"Không thấy {f}")
        data = json.loads(f.read_text(encoding="utf-8"))
        if "clips" not in data and data.get("clip"):
            data["clips"] = [data["clip"]]     # legacy single-clip project
        data.setdefault("clips", [])
        data["images"] = data.get("images") or []
        _sanitize(data)
        p = cls(dir=dir, **{k: data[k] for k in _FIELDS if k in data})
        if p.niche not in NICHES:
            raise BadInput(f"Ngành không hợp lệ: {p.niche}")
        if not p.clips:
            raise BadInput("Project chưa có clip nào")
        if len(p.clips) > MAX_CLIPS:
            raise BadInput(f"Tối đa {MAX_CLIPS} clip, project có {len(p.clips)}")
        if len(p.images) > MAX_IMAGES:
            raise BadInput(f"Tối đa {MAX_IMAGES} ảnh, project có {len(p.images)}")
        for name in [*p.clips, *p.images, *(n for n in (p.logo, p.music) if n)]:
            _check_name(name)
        if require_media:
            for name in p.clips:
                if not (p.input_dir / name).is_file():
                    raise BadInput(f"Không thấy file clip {name} trong project")
            for name in p.images:
                if not (p.input_dir / name).is_file():
                    raise BadInput(f"Không thấy file ảnh {name} trong project")
        p.work_dir.mkdir(parents=True, exist_ok=True)
        return p

    def save(self) -> None:
        data = {k: v for k, v in asdict(self).items() if k in _FIELDS}
        atomic_write_text(self.dir / "project.json", json.dumps(data, ensure_ascii=False, indent=2))

    @property
    def voiceover_on(self) -> bool:
        return bool(self.voiceover and self.voiceover.get("enabled") and self.voiceover.get("voice_id"))

    @property
    def voice_id(self) -> str:
        return str((self.voiceover or {}).get("voice_id") or "")

    @property
    def length_range(self) -> tuple[float, float]:
        return LENGTHS.get(self.length, LENGTHS["medium"])

    @property
    def input_dir(self) -> Path:
        return self.dir / "input"

    @property
    def work_dir(self) -> Path:
        return self.dir / "work"

    @property
    def clip_paths(self) -> list[Path]:
        return [self.input_dir / n for n in self.clips]

    @property
    def image_paths(self) -> list[Path]:
        return [self.input_dir / n for n in self.images]

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
