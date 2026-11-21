from dataclasses import dataclass, field

from autoedit.edl import Edl, VoiceLine
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
    frames_viewed: int = 0
    finished: bool = False
    aborted: bool = False
    summary: list[str] = field(default_factory=list)
    voice_lines: dict[tuple[float, str], VoiceLine] = field(default_factory=dict)
    voice_calls: int = 0
    fatal: Exception | None = None      # an error that must fail the run with its own code (e.g. VoiceAuth)
