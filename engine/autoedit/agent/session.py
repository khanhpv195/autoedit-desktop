from dataclasses import dataclass, field

from autoedit.edl import Edl
from autoedit.events import Emitter
from autoedit.prep import Prepared
from autoedit.project import Project


@dataclass
class EditSession:
    prepared: Prepared
    project: Project
    events: Emitter
    edl: Edl | None = None
    edl_errors: int = 0
    previews: int = 0
    finished: bool = False
    summary: list[str] = field(default_factory=list)
