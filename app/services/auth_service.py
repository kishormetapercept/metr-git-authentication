from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import quote

import httpx
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from starlette.requests import Request

from app.config import constants
from app.config.settings import Settings
from app.db.postgres import (
    add_allowed_user,
    allowed_user_exists,
    authorize_existing_github_user,
    ensure_auth_tables,
    ensure_bootstrap_admin_user,
    is_admin_user,
    verify_postgres_connection,
)
from app.exceptions import (
    BadRequestServiceError,
    ConflictServiceError,
    ForbiddenServiceError,
    ServiceError,
    UnauthorizedServiceError,
    UpstreamServiceError,
)
from app.utils.identity import normalize_email


def initialize_dependencies(settings: Settings) -> None:
    verify_postgres_connection(settings.postgres_dsn)
    ensure_auth_tables(settings.postgres_dsn)
    ensure_bootstrap_admin_user(settings.postgres_dsn)


def ensure_config(settings: Settings) -> None:
    if not settings.is_valid:
        raise ServiceError(constants.ERROR_CONFIG_MISSING, constants.HTTP_STATUS_SERVER_ERROR)


def _oauth_headers(token: str | None = None) -> dict[str, str]:
    headers = {constants.HEADER_ACCEPT: constants.HEADER_ACCEPT_JSON}
    if token:
        headers[constants.HEADER_AUTHORIZATION] = f'{constants.AUTH_BEARER_PREFIX} {token}'
    return headers


async def _require_admin_session_user(request: Request, settings: Settings) -> dict[str, Any]:
    session_user = request.session.get(constants.SESSION_USER_KEY)
    if not session_user:
        raise UnauthorizedServiceError(constants.ERROR_NOT_AUTHENTICATED, constants.HTTP_STATUS_UNAUTHORIZED)

    login = session_user.get(constants.SESSION_USER_FIELD_LOGIN)
    if not isinstance(login, str) or not login.strip():
        raise UnauthorizedServiceError(constants.ERROR_NOT_AUTHENTICATED, constants.HTTP_STATUS_UNAUTHORIZED)

    has_admin_access = await run_in_threadpool(is_admin_user, settings.postgres_dsn, login)
    if not has_admin_access:
        raise ForbiddenServiceError(constants.ERROR_ADMIN_REQUIRED, constants.HTTP_STATUS_FORBIDDEN)
    return session_user


async def _validate_github_user_and_email(git_username: str) -> tuple[str, str]:
    normalized_input = (git_username or '').strip()
    if not normalized_input:
        raise BadRequestServiceError('git_username is required.', constants.HTTP_STATUS_BAD_REQUEST)

    url = constants.GITHUB_PUBLIC_USER_URL_TEMPLATE.format(
        git_username=quote(normalized_input, safe=''),
    )
    try:
        async with httpx.AsyncClient(timeout=constants.HTTPX_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers={constants.HEADER_ACCEPT: constants.HEADER_ACCEPT_JSON})
    except httpx.RequestError as error:
        raise UpstreamServiceError(
            constants.ERROR_GITHUB_USERNAME_VALIDATION_FAILED,
            constants.HTTP_STATUS_BAD_GATEWAY,
        ) from error

    if response.status_code == constants.HTTP_STATUS_OK:
        payload = response.json()
        login = payload.get(constants.GITHUB_USER_FIELD_LOGIN)
        if not isinstance(login, str) or not login.strip():
            raise UpstreamServiceError(
                constants.ERROR_GITHUB_USERNAME_VALIDATION_FAILED,
                constants.HTTP_STATUS_BAD_GATEWAY,
            )

        email = payload.get(constants.GITHUB_EMAIL_FIELD_EMAIL)
        normalized_github_email = normalize_email(email)
        if normalized_github_email is None:
            raise BadRequestServiceError(
                constants.ERROR_GITHUB_EMAIL_NOT_PUBLIC,
                constants.HTTP_STATUS_BAD_REQUEST,
            )
        return login.strip(), normalized_github_email

    if response.status_code == constants.HTTP_STATUS_NOT_FOUND:
        raise BadRequestServiceError(constants.ERROR_GITHUB_USERNAME_NOT_FOUND, constants.HTTP_STATUS_BAD_REQUEST)

    raise UpstreamServiceError(
        constants.ERROR_GITHUB_USERNAME_VALIDATION_FAILED,
        constants.HTTP_STATUS_BAD_GATEWAY,
    )


async def build_login_response(request: Request, redirect: bool, settings: Settings) -> Any:
    ensure_config(settings)

    existing_user = request.session.get(constants.SESSION_USER_KEY)
    if existing_user:
        return {
            constants.RESPONSE_KEY_AUTHENTICATED: True,
            constants.RESPONSE_KEY_USER: existing_user,
        }

    state = secrets.token_urlsafe(constants.OAUTH_STATE_TOKEN_LENGTH)
    request.session[constants.SESSION_OAUTH_STATE_KEY] = state

    url = constants.OAUTH_AUTHORIZE_URL_TEMPLATE.format(
        base=constants.GITHUB_AUTHORIZE_URL,
        client_id=settings.github_client_id,
        redirect_uri=settings.github_redirect_uri,
        scope=constants.OAUTH_SCOPE,
        state=state,
    )
    if redirect:
        return RedirectResponse(url=url)

    return {
        constants.RESPONSE_KEY_AUTHENTICATED: False,
        constants.RESPONSE_KEY_AUTHORIZATION_URL: url,
        constants.RESPONSE_KEY_NEXT: constants.LOGIN_NEXT_MESSAGE,
    }


async def register_allowed_user(
    request: Request,
    settings: Settings,
    git_username: str,
    email: str,
) -> dict[str, Any]:
    ensure_config(settings)
    await _require_admin_session_user(request, settings)

    normalized_email = normalize_email(email)
    if normalized_email is None:
        raise BadRequestServiceError(constants.ERROR_EMAIL_REQUIRED, constants.HTTP_STATUS_BAD_REQUEST)

    exists_in_local_db = await run_in_threadpool(allowed_user_exists, settings.postgres_dsn, git_username)
    if exists_in_local_db:
        raise ConflictServiceError(constants.USER_ALREADY_EXISTS_MESSAGE, constants.HTTP_STATUS_CONFLICT)

    valid_github_username, github_email = await _validate_github_user_and_email(git_username)
    if normalized_email != github_email:
        raise BadRequestServiceError(constants.ERROR_GITHUB_EMAIL_MISMATCH, constants.HTTP_STATUS_BAD_REQUEST)

    try:
        return await run_in_threadpool(
            add_allowed_user,
            settings.postgres_dsn,
            valid_github_username,
            github_email,
        )
    except ValueError as error:
        raise BadRequestServiceError(str(error), constants.HTTP_STATUS_BAD_REQUEST) from error
    except Exception as error:
        raise ServiceError(constants.ERROR_USER_PERSISTENCE_FAILED, constants.HTTP_STATUS_SERVER_ERROR) from error


async def handle_auth_callback(
    request: Request,
    settings: Settings,
    code: str,
    state: str,
) -> dict[str, Any]:
    ensure_config(settings)

    expected_state = request.session.get(constants.SESSION_OAUTH_STATE_KEY)
    if not expected_state or expected_state != state:
        raise BadRequestServiceError(constants.ERROR_INVALID_OAUTH_STATE, constants.HTTP_STATUS_BAD_REQUEST)

    async with httpx.AsyncClient(timeout=constants.HTTPX_TIMEOUT_SECONDS) as client:
        token_response = await client.post(
            constants.GITHUB_ACCESS_TOKEN_URL,
            headers=_oauth_headers(),
            data={
                constants.GITHUB_TOKEN_REQUEST_FIELD_CLIENT_ID: settings.github_client_id,
                constants.GITHUB_TOKEN_REQUEST_FIELD_CLIENT_SECRET: settings.github_client_secret,
                constants.GITHUB_TOKEN_REQUEST_FIELD_CODE: code,
                constants.GITHUB_TOKEN_REQUEST_FIELD_REDIRECT_URI: settings.github_redirect_uri,
                constants.GITHUB_TOKEN_REQUEST_FIELD_STATE: state,
            },
        )
        if token_response.status_code >= constants.HTTP_STATUS_BAD_REQUEST:
            raise UpstreamServiceError(constants.ERROR_TOKEN_EXCHANGE_FAILED, constants.HTTP_STATUS_BAD_GATEWAY)

        token_data = token_response.json()
        access_token = token_data.get(constants.GITHUB_TOKEN_FIELD_ACCESS_TOKEN)
        if not access_token:
            raise UpstreamServiceError(constants.ERROR_ACCESS_TOKEN_MISSING, constants.HTTP_STATUS_BAD_GATEWAY)

        user_response = await client.get(constants.GITHUB_USER_URL, headers=_oauth_headers(access_token))
        if user_response.status_code >= constants.HTTP_STATUS_BAD_REQUEST:
            raise UpstreamServiceError(constants.ERROR_PROFILE_FETCH_FAILED, constants.HTTP_STATUS_BAD_GATEWAY)
        user = user_response.json()

        email_response = await client.get(constants.GITHUB_USER_EMAILS_URL, headers=_oauth_headers(access_token))
        email = None
        if email_response.status_code < constants.HTTP_STATUS_BAD_REQUEST:
            emails = email_response.json()
            primary = next((e for e in emails if e.get(constants.GITHUB_EMAIL_FIELD_PRIMARY)), None)
            verified = next((e for e in emails if e.get(constants.GITHUB_EMAIL_FIELD_VERIFIED)), None)
            chosen = primary or verified or (emails[0] if emails else None)
            if chosen:
                email = chosen.get(constants.GITHUB_EMAIL_FIELD_EMAIL)

    try:
        session_user = await run_in_threadpool(
            authorize_existing_github_user,
            settings.postgres_dsn,
            user,
            email,
        )
    except PermissionError as error:
        raise ForbiddenServiceError(constants.ERROR_USER_NOT_ALLOWED, constants.HTTP_STATUS_FORBIDDEN) from error
    except Exception as error:
        raise ServiceError(constants.ERROR_USER_PERSISTENCE_FAILED, constants.HTTP_STATUS_SERVER_ERROR) from error

    request.session[constants.SESSION_USER_KEY] = session_user
    request.session.pop(constants.SESSION_OAUTH_STATE_KEY, None)

    return {
        constants.RESPONSE_KEY_MESSAGE: constants.AUTH_SUCCESS_MESSAGE,
        constants.RESPONSE_KEY_USER: session_user,
    }


def get_current_user_response(request: Request) -> dict[str, Any]:
    user = request.session.get(constants.SESSION_USER_KEY)
    if not user:
        raise UnauthorizedServiceError(constants.ERROR_NOT_AUTHENTICATED, constants.HTTP_STATUS_UNAUTHORIZED)
    return {
        constants.RESPONSE_KEY_AUTHENTICATED: True,
        constants.RESPONSE_KEY_USER: user,
    }


def logout_session(request: Request) -> dict[str, str]:
    request.session.clear()
    return {constants.RESPONSE_KEY_MESSAGE: constants.LOGOUT_MESSAGE}

