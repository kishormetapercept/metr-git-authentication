from pathlib import Path

CONFIG_FILENAME = 'config.yaml'
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / CONFIG_FILENAME

CONFIG_KEY_GITHUB_CLIENT_ID = 'github_client_id'
CONFIG_KEY_GITHUB_CLIENT_SECRET = 'github_client_secret'
CONFIG_KEY_GITHUB_REDIRECT_URI = 'github_redirect_uri'
CONFIG_KEY_SECRET_KEY = 'secret_key'
CONFIG_KEY_SESSION_HTTPS_ONLY = 'session_https_only'
CONFIG_KEY_POSTGRES_DSN = 'postgres_dsn'

DEFAULT_EMPTY_STRING = ''
DEFAULT_GITHUB_REDIRECT_URI = 'http://127.0.0.1:8000/auth/callback'
DEFAULT_SESSION_HTTPS_ONLY = False

TRUTHY_STRINGS = {'1', 'true', 'yes', 'on'}

APP_TITLE = 'GitHub Auth Service'
APP_VERSION = '1.0.0'

ROUTE_HEALTH = '/health'
ROUTE_INDEX = '/'
ROUTE_LOGIN = '/login'
ROUTE_AUTH_CALLBACK = '/auth/callback'
ROUTE_ME = '/me'
ROUTE_LOGOUT = '/logout'
ROUTE_ADMIN_USERS = '/admin/register'

SESSION_SECRET_FALLBACK = 'dev-secret-change-me'
SESSION_SAME_SITE = 'lax'
SESSION_USER_KEY = 'user'
SESSION_OAUTH_STATE_KEY = 'oauth_state'

SESSION_USER_FIELD_ID = 'id'
SESSION_USER_FIELD_LOGIN = 'login'

RESPONSE_KEY_STATUS = 'status'
RESPONSE_KEY_MESSAGE = 'message'
RESPONSE_KEY_AUTHENTICATED = 'authenticated'
RESPONSE_KEY_USER = 'user'
RESPONSE_KEY_AUTHORIZATION_URL = 'authorization_url'
RESPONSE_KEY_NEXT = 'next'

RESPONSE_STATUS_OK = 'ok'
INDEX_MESSAGE = 'Use /login to authenticate with GitHub'
LOGIN_NEXT_MESSAGE = 'Open authorization_url in browser and complete consent, then call /auth/callback.'
AUTH_SUCCESS_MESSAGE = 'Authentication successful'
LOGOUT_MESSAGE = 'Logged out'
USER_PROVISIONED_MESSAGE = 'User provisioned successfully'
USER_ALREADY_EXISTS_MESSAGE = 'User is already registered'

HTTP_STATUS_OK = 200
HTTP_STATUS_BAD_REQUEST = 400
HTTP_STATUS_UNAUTHORIZED = 401
HTTP_STATUS_FORBIDDEN = 403
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_CONFLICT = 409
HTTP_STATUS_SERVER_ERROR = 500
HTTP_STATUS_BAD_GATEWAY = 502

ERROR_CONFIG_MISSING = 'Service is not configured. Check required fields in config.yaml.'
ERROR_INVALID_OAUTH_STATE = 'Invalid OAuth state'
ERROR_TOKEN_EXCHANGE_FAILED = 'Failed to exchange OAuth token'
ERROR_ACCESS_TOKEN_MISSING = 'No access token returned by GitHub'
ERROR_PROFILE_FETCH_FAILED = 'Failed to fetch GitHub profile'
ERROR_NOT_AUTHENTICATED = 'Not authenticated'
ERROR_USER_PERSISTENCE_FAILED = 'Failed to persist authenticated user'
ERROR_USER_NOT_ALLOWED = 'User is not allowed to login'
ERROR_ADMIN_REQUIRED = 'Admin access required'
ERROR_GITHUB_USERNAME_NOT_FOUND = 'GitHub username does not exist'
ERROR_GITHUB_USERNAME_VALIDATION_FAILED = 'Failed to validate GitHub username'
ERROR_EMAIL_REQUIRED = 'email is required'
ERROR_GITHUB_EMAIL_NOT_PUBLIC = 'GitHub public email not available for this username'
ERROR_GITHUB_EMAIL_MISMATCH = 'Provided email does not match GitHub public email'

OAUTH_STATE_TOKEN_LENGTH = 24
OAUTH_SCOPE = 'read:user user:email'
OAUTH_AUTHORIZE_URL_TEMPLATE = (
    '{base}?client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}&state={state}'
)

HEADER_ACCEPT = 'Accept'
HEADER_AUTHORIZATION = 'Authorization'
HEADER_ACCEPT_JSON = 'application/json'
AUTH_BEARER_PREFIX = 'Bearer'

GITHUB_AUTHORIZE_URL = 'https://github.com/login/oauth/authorize'
GITHUB_ACCESS_TOKEN_URL = 'https://github.com/login/oauth/access_token'
GITHUB_USER_URL = 'https://api.github.com/user'
GITHUB_USER_EMAILS_URL = 'https://api.github.com/user/emails'
GITHUB_PUBLIC_USER_URL_TEMPLATE = 'https://api.github.com/users/{git_username}'

HTTPX_TIMEOUT_SECONDS = 15.0

GITHUB_TOKEN_FIELD_ACCESS_TOKEN = 'access_token'
GITHUB_TOKEN_REQUEST_FIELD_CLIENT_ID = 'client_id'
GITHUB_TOKEN_REQUEST_FIELD_CLIENT_SECRET = 'client_secret'
GITHUB_TOKEN_REQUEST_FIELD_CODE = 'code'
GITHUB_TOKEN_REQUEST_FIELD_REDIRECT_URI = 'redirect_uri'
GITHUB_TOKEN_REQUEST_FIELD_STATE = 'state'
GITHUB_EMAIL_FIELD_PRIMARY = 'primary'
GITHUB_EMAIL_FIELD_VERIFIED = 'verified'
GITHUB_EMAIL_FIELD_EMAIL = 'email'

GITHUB_USER_FIELD_ID = 'id'
GITHUB_USER_FIELD_LOGIN = 'login'
GITHUB_USER_FIELD_NAME = 'name'
GITHUB_USER_FIELD_AVATAR_URL = 'avatar_url'
GITHUB_USER_FIELD_HTML_URL = 'html_url'

DEFAULT_ROLE_USER = 'user'
DEFAULT_ROLE_ADMIN = 'admin'

BOOTSTRAP_ADMIN_GITHUB_ID = 250086117
BOOTSTRAP_ADMIN_LOGIN = 'kishormetapercept'
BOOTSTRAP_ADMIN_EMAIL = 'kishor.bg@metapercept.com'

