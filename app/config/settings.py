from functools import lru_cache
from typing import Any

import yaml

from app.config import constants


def _load_yaml_config(path=constants.CONFIG_PATH) -> dict[str, Any]:
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
        return value.strip().lower() in constants.TRUTHY_STRINGS
    if isinstance(value, (int, float)):
        return bool(value)
    return default


class Settings:
    def __init__(self) -> None:
        config = _load_yaml_config()

        self.github_client_id = str(
            config.get(constants.CONFIG_KEY_GITHUB_CLIENT_ID, constants.DEFAULT_EMPTY_STRING)
        ).strip()
        self.github_client_secret = str(
            config.get(constants.CONFIG_KEY_GITHUB_CLIENT_SECRET, constants.DEFAULT_EMPTY_STRING)
        ).strip()
        self.github_redirect_uri = str(
            config.get(constants.CONFIG_KEY_GITHUB_REDIRECT_URI, constants.DEFAULT_GITHUB_REDIRECT_URI)
        ).strip()
        self.secret_key = str(config.get(constants.CONFIG_KEY_SECRET_KEY, constants.DEFAULT_EMPTY_STRING)).strip()
        self.postgres_dsn = str(config.get(constants.CONFIG_KEY_POSTGRES_DSN, constants.DEFAULT_EMPTY_STRING)).strip()
        self.session_https_only = _to_bool(
            config.get(constants.CONFIG_KEY_SESSION_HTTPS_ONLY, constants.DEFAULT_SESSION_HTTPS_ONLY)
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

