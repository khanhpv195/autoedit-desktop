"""Map Claude Agent SDK failures to our error codes (NO_AUTH, RATE_LIMIT, SETUP_REQUIRED)."""
from claude_agent_sdk import CLINotFoundError, ProcessError, ResultError, ResultMessage

from autoedit.errors import AutoeditError, NoAuth, RateLimited, SetupRequired

AUTH_WORDS = ("not logged in", "/login", "authentication", "invalid api key", "oauth token", "unauthorized")
# Not the bare "limit reached": the CLI also says "context limit reached" / "max turns", which are not quota problems.
LIMIT_WORDS = ("rate limit", "rate_limit", "usage limit", "too many requests", "hour limit", "weekly limit",
               "daily limit", "monthly limit")
NO_AUTH_MSG = "Tài khoản Claude chưa đăng nhập hoặc không dùng được"
RATE_MSG = "Đã hết lượt Claude của gói"


def classify_text(text: str, status: int | None = None, reset_at: str | None = None) -> AutoeditError | None:
    low = (text or "").lower()
    if status == 429 or any(w in low for w in LIMIT_WORDS):
        return RateLimited(RATE_MSG, reset_at)
    if status in (401, 403) or any(w in low for w in AUTH_WORDS):
        return NoAuth(NO_AUTH_MSG)
    return None


def classify_result(msg: ResultMessage, reset_at: str | None = None) -> AutoeditError | None:
    if not msg.is_error:
        return None
    text = " ".join([msg.result or "", *(msg.errors or [])])
    return classify_text(text, msg.api_error_status, reset_at)


def classify_sdk_error(e: BaseException, reset_at: str | None = None) -> AutoeditError | None:
    if isinstance(e, AutoeditError):
        return e
    if isinstance(e, CLINotFoundError):
        return SetupRequired("Chưa tải Claude, hãy chạy lại bước cài đặt")
    if isinstance(e, ResultError):
        text = " ".join([e.result or "", *e.errors, str(e)])
        return classify_text(text, e.api_error_status, reset_at)
    if isinstance(e, ProcessError):
        return classify_text(f"{e} {e.stderr or ''}", None, reset_at)
    return None
