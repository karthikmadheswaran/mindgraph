import os

from posthog import Posthog

_client = None


def get_posthog() -> Posthog | None:
    global _client
    if _client is None:
        api_key = os.environ.get("POSTHOG_API_KEY")
        host = os.environ.get("POSTHOG_HOST", "https://us.i.posthog.com")
        if api_key:
            _client = Posthog(api_key, host=host)
    return _client


def track(user_id: str, event: str, properties: dict = {}) -> None:
    """Fire-and-forget analytics event. Never raises — analytics must never break the app."""
    try:
        ph = get_posthog()
        if ph:
            ph.capture(user_id, event, properties)
    except Exception:
        pass
