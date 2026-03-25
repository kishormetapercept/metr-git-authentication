from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, get_settings
from app.constants import app as app_constants
from app.db.postgres import (
    add_allowed_user,
    allowed_user_exists,
    authorize_existing_github_user,
    ensure_auth_tables,
    ensure_bootstrap_admin_user,
    is_admin_user,
    verify_postgres_connection,
)

settings = get_settings()

app = FastAPI(title=app_constants.APP_TITLE, version=app_constants.APP_VERSION)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key or app_constants.SESSION_SECRET_FALLBACK,
    https_only=settings.session_https_only,
    same_site=app_constants.SESSION_SAME_SITE,
)


@app.on_event('startup')
async def verify_dependencies() -> None:
    verify_postgres_connection(settings.postgres_dsn)
    ensure_auth_tables(settings.postgres_dsn)
    ensure_bootstrap_admin_user(settings.postgres_dsn)


def settings_dependency() -> Settings:
    return get_settings()


class ProvisionUserRequest(BaseModel):
    git_username: str
    email: str


def _require_config(settings: Settings) -> None:
    if not settings.is_valid:
        raise HTTPException(
            status_code=app_constants.HTTP_STATUS_SERVER_ERROR,
            detail=app_constants.ERROR_CONFIG_MISSING,
        )


def _oauth_headers(token: str | None = None) -> dict[str, str]:
    headers = {app_constants.HEADER_ACCEPT: app_constants.HEADER_ACCEPT_JSON}
    if token:
        headers[app_constants.HEADER_AUTHORIZATION] = f'{app_constants.AUTH_BEARER_PREFIX} {token}'
    return headers


async def _require_admin_session_user(request: Request, settings: Settings) -> dict[str, Any]:
    session_user = request.session.get(app_constants.SESSION_USER_KEY)
    if not session_user:
        raise HTTPException(status_code=app_constants.HTTP_STATUS_UNAUTHORIZED, detail=app_constants.ERROR_NOT_AUTHENTICATED)

    login = session_user.get(app_constants.SESSION_USER_FIELD_LOGIN)
    if not isinstance(login, str) or not login.strip():
        raise HTTPException(status_code=app_constants.HTTP_STATUS_UNAUTHORIZED, detail=app_constants.ERROR_NOT_AUTHENTICATED)

    has_admin_access = await run_in_threadpool(is_admin_user, settings.postgres_dsn, login)
    if not has_admin_access:
        raise HTTPException(status_code=app_constants.HTTP_STATUS_FORBIDDEN, detail=app_constants.ERROR_ADMIN_REQUIRED)

    return session_user


def _normalize_email(value: str) -> str:
    return value.strip().lower()


async def _validate_github_user_and_email(git_username: str) -> tuple[str, str]:
    normalized_input = (git_username or '').strip()
    if not normalized_input:
        raise HTTPException(status_code=app_constants.HTTP_STATUS_BAD_REQUEST, detail='git_username is required.')

    url = app_constants.GITHUB_PUBLIC_USER_URL_TEMPLATE.format(
        git_username=quote(normalized_input, safe=''),
    )
    try:
        async with httpx.AsyncClient(timeout=app_constants.HTTPX_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                headers={app_constants.HEADER_ACCEPT: app_constants.HEADER_ACCEPT_JSON},
            )
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=app_constants.HTTP_STATUS_BAD_GATEWAY,
            detail=app_constants.ERROR_GITHUB_USERNAME_VALIDATION_FAILED,
        ) from error

    if response.status_code == app_constants.HTTP_STATUS_OK:
        payload = response.json()
        login = payload.get(app_constants.GITHUB_USER_FIELD_LOGIN)
        if not isinstance(login, str) or not login.strip():
            raise HTTPException(
                status_code=app_constants.HTTP_STATUS_BAD_GATEWAY,
                detail=app_constants.ERROR_GITHUB_USERNAME_VALIDATION_FAILED,
            )
        email = payload.get(app_constants.GITHUB_EMAIL_FIELD_EMAIL)
        if not isinstance(email, str) or not email.strip():
            raise HTTPException(
                status_code=app_constants.HTTP_STATUS_BAD_REQUEST,
                detail=app_constants.ERROR_GITHUB_EMAIL_NOT_PUBLIC,
            )
        return login.strip(), _normalize_email(email)

    if response.status_code == app_constants.HTTP_STATUS_NOT_FOUND:
        raise HTTPException(
            status_code=app_constants.HTTP_STATUS_BAD_REQUEST,
            detail=app_constants.ERROR_GITHUB_USERNAME_NOT_FOUND,
        )

    raise HTTPException(
        status_code=app_constants.HTTP_STATUS_BAD_GATEWAY,
        detail=app_constants.ERROR_GITHUB_USERNAME_VALIDATION_FAILED,
    )


@app.get(app_constants.ROUTE_HEALTH)
async def health() -> dict[str, str]:
    return {app_constants.RESPONSE_KEY_STATUS: app_constants.RESPONSE_STATUS_OK}


@app.get(app_constants.ROUTE_INDEX)
async def index() -> dict[str, str]:
    return {app_constants.RESPONSE_KEY_MESSAGE: app_constants.INDEX_MESSAGE}


@app.get(app_constants.ROUTE_LOGIN, response_model=None)
async def login(
    request: Request,
    redirect: bool = False,
    settings: Settings = Depends(settings_dependency),
) -> Any:
    _require_config(settings)

    existing_user = request.session.get(app_constants.SESSION_USER_KEY)
    if existing_user:
        return {app_constants.RESPONSE_KEY_AUTHENTICATED: True, app_constants.RESPONSE_KEY_USER: existing_user}

    state = secrets.token_urlsafe(app_constants.OAUTH_STATE_TOKEN_LENGTH)
    request.session[app_constants.SESSION_OAUTH_STATE_KEY] = state

    url = app_constants.OAUTH_AUTHORIZE_URL_TEMPLATE.format(
        base=app_constants.GITHUB_AUTHORIZE_URL,
        client_id=settings.github_client_id,
        redirect_uri=settings.github_redirect_uri,
        scope=app_constants.OAUTH_SCOPE,
        state=state,
    )
    if redirect:
        return RedirectResponse(url=url)
    return {
        app_constants.RESPONSE_KEY_AUTHENTICATED: False,
        app_constants.RESPONSE_KEY_AUTHORIZATION_URL: url,
        app_constants.RESPONSE_KEY_NEXT: app_constants.LOGIN_NEXT_MESSAGE,
    }


@app.post(app_constants.ROUTE_ADMIN_USERS)
async def provision_user(
    payload: ProvisionUserRequest,
    request: Request,
    settings: Settings = Depends(settings_dependency),
) -> dict[str, Any]:
    _require_config(settings)
    await _require_admin_session_user(request, settings)
    if not payload.email or not payload.email.strip():
        raise HTTPException(
            status_code=app_constants.HTTP_STATUS_BAD_REQUEST,
            detail=app_constants.ERROR_EMAIL_REQUIRED,
        )

    exists_in_local_db = await run_in_threadpool(
        allowed_user_exists,
        settings.postgres_dsn,
        payload.git_username,
    )
    if exists_in_local_db:
        raise HTTPException(
            status_code=app_constants.HTTP_STATUS_CONFLICT,
            detail=app_constants.USER_ALREADY_EXISTS_MESSAGE,
        )

    valid_github_username, github_email = await _validate_github_user_and_email(payload.git_username)
    if _normalize_email(payload.email) != github_email:
        raise HTTPException(
            status_code=app_constants.HTTP_STATUS_BAD_REQUEST,
            detail=app_constants.ERROR_GITHUB_EMAIL_MISMATCH,
        )

    try:
        provisioned_user = await run_in_threadpool(
            add_allowed_user,
            settings.postgres_dsn,
            valid_github_username,
            github_email,
        )
    except ValueError as error:
        raise HTTPException(status_code=app_constants.HTTP_STATUS_BAD_REQUEST, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=app_constants.HTTP_STATUS_SERVER_ERROR,
            detail=app_constants.ERROR_USER_PERSISTENCE_FAILED,
        ) from error

    return {
        app_constants.RESPONSE_KEY_MESSAGE: app_constants.USER_PROVISIONED_MESSAGE,
        app_constants.RESPONSE_KEY_USER: provisioned_user,
    }


@app.get(app_constants.ROUTE_AUTH_CALLBACK)
async def auth_callback(
    request: Request,
    code: str,
    state: str,
    settings: Settings = Depends(settings_dependency),
) -> dict[str, Any]:
    _require_config(settings)

    expected_state = request.session.get(app_constants.SESSION_OAUTH_STATE_KEY)
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=app_constants.HTTP_STATUS_BAD_REQUEST, detail=app_constants.ERROR_INVALID_OAUTH_STATE)

    async with httpx.AsyncClient(timeout=app_constants.HTTPX_TIMEOUT_SECONDS) as client:
        token_response = await client.post(
            app_constants.GITHUB_ACCESS_TOKEN_URL,
            headers=_oauth_headers(),
            data={
                app_constants.GITHUB_TOKEN_REQUEST_FIELD_CLIENT_ID: settings.github_client_id,
                app_constants.GITHUB_TOKEN_REQUEST_FIELD_CLIENT_SECRET: settings.github_client_secret,
                app_constants.GITHUB_TOKEN_REQUEST_FIELD_CODE: code,
                app_constants.GITHUB_TOKEN_REQUEST_FIELD_REDIRECT_URI: settings.github_redirect_uri,
                app_constants.GITHUB_TOKEN_REQUEST_FIELD_STATE: state,
            },
        )

        if token_response.status_code >= app_constants.HTTP_STATUS_BAD_REQUEST:
            raise HTTPException(status_code=app_constants.HTTP_STATUS_BAD_GATEWAY, detail=app_constants.ERROR_TOKEN_EXCHANGE_FAILED)

        token_data = token_response.json()
        access_token = token_data.get(app_constants.GITHUB_TOKEN_FIELD_ACCESS_TOKEN)
        if not access_token:
            raise HTTPException(status_code=app_constants.HTTP_STATUS_BAD_GATEWAY, detail=app_constants.ERROR_ACCESS_TOKEN_MISSING)

        user_response = await client.get(
            app_constants.GITHUB_USER_URL,
            headers=_oauth_headers(access_token),
        )
        if user_response.status_code >= app_constants.HTTP_STATUS_BAD_REQUEST:
            raise HTTPException(status_code=app_constants.HTTP_STATUS_BAD_GATEWAY, detail=app_constants.ERROR_PROFILE_FETCH_FAILED)

        user = user_response.json()

        email_response = await client.get(
            app_constants.GITHUB_USER_EMAILS_URL,
            headers=_oauth_headers(access_token),
        )
        email = None
        if email_response.status_code < app_constants.HTTP_STATUS_BAD_REQUEST:
            emails = email_response.json()
            primary = next((e for e in emails if e.get(app_constants.GITHUB_EMAIL_FIELD_PRIMARY)), None)
            verified = next((e for e in emails if e.get(app_constants.GITHUB_EMAIL_FIELD_VERIFIED)), None)
            chosen = primary or verified or (emails[0] if emails else None)
            if chosen:
                email = chosen.get(app_constants.GITHUB_EMAIL_FIELD_EMAIL)

    try:
        session_user = await run_in_threadpool(
            authorize_existing_github_user,
            settings.postgres_dsn,
            user,
            email,
        )
    except PermissionError as error:
        raise HTTPException(
            status_code=app_constants.HTTP_STATUS_FORBIDDEN,
            detail=app_constants.ERROR_USER_NOT_ALLOWED,
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=app_constants.HTTP_STATUS_SERVER_ERROR,
            detail=app_constants.ERROR_USER_PERSISTENCE_FAILED,
        ) from error
    request.session[app_constants.SESSION_USER_KEY] = session_user
    request.session.pop(app_constants.SESSION_OAUTH_STATE_KEY, None)

    return {app_constants.RESPONSE_KEY_MESSAGE: app_constants.AUTH_SUCCESS_MESSAGE, app_constants.RESPONSE_KEY_USER: session_user}


@app.get(app_constants.ROUTE_ME)
async def me(request: Request) -> dict[str, Any]:
    user = request.session.get(app_constants.SESSION_USER_KEY)
    if not user:
        raise HTTPException(status_code=app_constants.HTTP_STATUS_UNAUTHORIZED, detail=app_constants.ERROR_NOT_AUTHENTICATED)
    return {app_constants.RESPONSE_KEY_AUTHENTICATED: True, app_constants.RESPONSE_KEY_USER: user}


@app.post(app_constants.ROUTE_LOGOUT)
async def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {app_constants.RESPONSE_KEY_MESSAGE: app_constants.LOGOUT_MESSAGE}

