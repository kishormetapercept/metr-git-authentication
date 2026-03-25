from __future__ import annotations

import secrets
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, get_settings
from app.constants import app as app_constants

settings = get_settings()

app = FastAPI(title=app_constants.APP_TITLE, version=app_constants.APP_VERSION)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key or app_constants.SESSION_SECRET_FALLBACK,
    https_only=settings.session_https_only,
    same_site=app_constants.SESSION_SAME_SITE,
)


def settings_dependency() -> Settings:
    return get_settings()


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

    session_user = {
        app_constants.SESSION_USER_FIELD_ID: user.get(app_constants.GITHUB_USER_FIELD_ID),
        app_constants.SESSION_USER_FIELD_LOGIN: user.get(app_constants.GITHUB_USER_FIELD_LOGIN),
        app_constants.SESSION_USER_FIELD_NAME: user.get(app_constants.GITHUB_USER_FIELD_NAME),
        app_constants.SESSION_USER_FIELD_AVATAR_URL: user.get(app_constants.GITHUB_USER_FIELD_AVATAR_URL),
        app_constants.SESSION_USER_FIELD_PROFILE_URL: user.get(app_constants.GITHUB_USER_FIELD_HTML_URL),
        app_constants.GITHUB_EMAIL_FIELD_EMAIL: email,
    }
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

