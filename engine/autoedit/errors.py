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


class SocialAuth(AutoeditError):
    code = "SOCIAL_AUTH"


class SocialLimit(AutoeditError):
    code = "SOCIAL_LIMIT"


class SocialFailed(AutoeditError):
    code = "SOCIAL_FAILED"


class VoiceAuth(AutoeditError):
    code = "VOICE_AUTH"


class VoiceQuota(AutoeditError):
    code = "VOICE_QUOTA"


class VoiceMissing(AutoeditError):
    code = "VOICE_MISSING"


class VoiceLimit(AutoeditError):
    code = "VOICE_LIMIT"


class VoiceFailed(AutoeditError):
    code = "VOICE_FAILED"
