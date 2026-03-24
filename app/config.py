from functools import lru_cache
import os

from dotenv import find_dotenv, load_dotenv


load_dotenv(find_dotenv(), encoding='utf-8-sig')


class Settings:
    def __init__(self) -> None:
        self.github_client_id = os.getenv('GITHUB_CLIENT_ID', '')
        self.github_client_secret = os.getenv('GITHUB_CLIENT_SECRET', '')
        self.github_redirect_uri = os.getenv('GITHUB_REDIRECT_URI', 'http://127.0.0.1:8000/auth/callback')
        self.secret_key = os.getenv('SECRET_KEY', '')
        self.session_https_only = os.getenv('SESSION_HTTPS_ONLY', 'false').lower() == 'true'

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
