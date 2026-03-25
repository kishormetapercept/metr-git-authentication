from typing import Any


def normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_git_username(value: Any) -> str | None:
    username = normalize_optional_text(value)
    if username is None:
        return None
    return username.lower()


def normalize_email(value: Any) -> str | None:
    email = normalize_optional_text(value)
    if email is None:
        return None
    return email.lower()

