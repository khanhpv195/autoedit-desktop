class AutoeditError(Exception):
    code = "AGENT_FAILED"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadInput(AutoeditError):
    code = "BAD_INPUT"


class NoAuth(AutoeditError):
    code = "NO_AUTH"


class RenderFailed(AutoeditError):
    code = "RENDER_FAILED"


class AgentFailed(AutoeditError):
    code = "AGENT_FAILED"


class SetupRequired(AutoeditError):
    code = "SETUP_REQUIRED"


class RateLimited(AutoeditError):
    code = "RATE_LIMIT"

    def __init__(self, message: str, retry_at: str | None = None):
        super().__init__(message)
        self.retry_at = retry_at
