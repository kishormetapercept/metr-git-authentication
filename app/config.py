from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config.yaml'


def _load_yaml_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
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
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


class Settings:
    def __init__(self) -> None:
        config = _load_yaml_config()

        self.github_client_id = str(config.get('github_client_id', '')).strip()
        self.github_client_secret = str(config.get('github_client_secret', '')).strip()
        self.github_redirect_uri = str(
            config.get('github_redirect_uri', 'http://127.0.0.1:8000/auth/callback')
        ).strip()
        self.secret_key = str(config.get('secret_key', '')).strip()
        self.session_https_only = _to_bool(config.get('session_https_only', False))

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
