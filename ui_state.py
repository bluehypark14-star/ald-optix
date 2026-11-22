"""Pure client-UI state validator; can be tested without importing Streamlit."""


def workflow_is_current(saved: object, request: str | dict, mode: str) -> bool:
    """A saved workflow must never be presented for edited inputs or a changed mode."""
    return (isinstance(saved, dict)
            and saved.get('request') == request
            and saved.get('mode') == mode
            and isinstance(saved.get('response'), str)
            and isinstance(saved.get('trace'), list))
