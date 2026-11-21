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


class VoiceError(AutoeditError):
    """Base of the voiceover errors: an edit with voiceover on fails with these, it never falls back silently."""
    code = "VOICE_FAILED"


class VoiceAuth(VoiceError):
    code = "VOICE_AUTH"


class VoiceQuota(VoiceError):
    code = "VOICE_QUOTA"


class VoiceMissing(VoiceError):
    code = "VOICE_MISSING"


class VoiceLimit(VoiceError):
    code = "VOICE_LIMIT"


class VoiceFailed(VoiceError):
    code = "VOICE_FAILED"
