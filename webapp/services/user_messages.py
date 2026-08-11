"""Map internal errors to user-facing product copy."""

USER_UNAVAILABLE = "Unable to start this campaign. Please try again later."
USER_PROCESS_FAILED = "Unable to process this request right now."
USER_IMPORT_FAILED = "Unable to read that file. Please check the format and try again."
USER_GENERIC = "Something went wrong. Please try again."


def sanitize_public_detail(detail: str | None) -> str:
    if not detail:
        return USER_GENERIC
    text = detail.lower()
    technical = (
        "twilio", "kokoro", "tts", "python", "pipeline", "inference",
        "socket", "traceback", "module named", ".env",
    )
    if any(t in text for t in technical):
        if "credential" in text or "reach" in text or "available" in text or "connect" in text:
            return USER_UNAVAILABLE
        return USER_PROCESS_FAILED
    # Keep short non-technical messages
    if len(detail) > 160:
        return USER_GENERIC
    return detail
