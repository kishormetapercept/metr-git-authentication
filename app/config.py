from functools import lru_cache
from typing import Any

import yaml

from app.constants.config import (
    CONFIG_KEY_GITHUB_CLIENT_ID,
    CONFIG_KEY_GITHUB_CLIENT_SECRET,
    CONFIG_KEY_GITHUB_REDIRECT_URI,
    CONFIG_KEY_SECRET_KEY,
    CONFIG_KEY_SESSION_HTTPS_ONLY,
    CONFIG_PATH,
    DEFAULT_EMPTY_STRING,
    DEFAULT_GITHUB_REDIRECT_URI,
    DEFAULT_SESSION_HTTPS_ONLY,
    TRUTHY_STRINGS,
)


def _load_yaml_config(path=CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open('r', encoding='utf-8') as config_file:
        data = yaml.safe_load(config_file) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_STRINGS
    if isinstance(value, (int, float)):
        return bool(value)
    return default


class Settings:
    def __init__(self) -> None:
        config = _load_yaml_config()

        self.github_client_id = str(config.get(CONFIG_KEY_GITHUB_CLIENT_ID, DEFAULT_EMPTY_STRING)).strip()
        self.github_client_secret = str(
            config.get(CONFIG_KEY_GITHUB_CLIENT_SECRET, DEFAULT_EMPTY_STRING)
        ).strip()
        self.github_redirect_uri = str(
            config.get(CONFIG_KEY_GITHUB_REDIRECT_URI, DEFAULT_GITHUB_REDIRECT_URI)
        ).strip()
        self.secret_key = str(config.get(CONFIG_KEY_SECRET_KEY, DEFAULT_EMPTY_STRING)).strip()
        self.session_https_only = _to_bool(
            config.get(CONFIG_KEY_SESSION_HTTPS_ONLY, DEFAULT_SESSION_HTTPS_ONLY)
        )

    @property
    def is_valid(self) -> bool:
        return bool(
            self.github_client_id
            and self.github_client_secret
            and self.secret_key
            and self.github_redirect_uri
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
