from pathlib import Path

CONFIG_FILENAME = 'config.yaml'
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / CONFIG_FILENAME

CONFIG_KEY_GITHUB_CLIENT_ID = 'github_client_id'
CONFIG_KEY_GITHUB_CLIENT_SECRET = 'github_client_secret'
CONFIG_KEY_GITHUB_REDIRECT_URI = 'github_redirect_uri'
CONFIG_KEY_SECRET_KEY = 'secret_key'
CONFIG_KEY_SESSION_HTTPS_ONLY = 'session_https_only'

DEFAULT_EMPTY_STRING = ''
DEFAULT_GITHUB_REDIRECT_URI = 'http://127.0.0.1:8000/auth/callback'
DEFAULT_SESSION_HTTPS_ONLY = False

TRUTHY_STRINGS = {'1', 'true', 'yes', 'on'}

