from __future__ import annotations

import secrets
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, get_settings

settings = get_settings()

app = FastAPI(title='GitHub Auth Service', version='1.0.0')
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key or 'dev-secret-change-me',
    https_only=settings.session_https_only,
    same_site='lax',
)


def settings_dependency() -> Settings:
    return get_settings()


def _require_config(settings: Settings) -> None:
    if not settings.is_valid:
        raise HTTPException(
            status_code=500,
            detail='Service is not configured. Check required environment variables.',
        )


def _oauth_headers(token: str | None = None) -> dict[str, str]:
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


@app.get('/health')
async def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.get('/')
async def index() -> dict[str, str]:
    return {'message': 'Use /login to authenticate with GitHub'}


@app.get('/login', response_model=None)
async def login(
    request: Request,
    redirect: bool = False,
    settings: Settings = Depends(settings_dependency),
) -> Any:
    _require_config(settings)

    existing_user = request.session.get('user')
    if existing_user:
        return {'authenticated': True, 'user': existing_user}

    state = secrets.token_urlsafe(24)
    request.session['oauth_state'] = state

    url = (
        'https://github.com/login/oauth/authorize'
        f'?client_id={settings.github_client_id}'
        f'&redirect_uri={settings.github_redirect_uri}'
        '&scope=read:user user:email'
        f'&state={state}'
    )
    if redirect:
        return RedirectResponse(url=url)
    return {
        'authenticated': False,
        'authorization_url': url,
        'next': 'Open authorization_url in browser and complete consent, then call /auth/callback.',
    }


@app.get('/auth/callback')
async def auth_callback(
    request: Request,
    code: str,
    state: str,
    settings: Settings = Depends(settings_dependency),
) -> dict[str, Any]:
    _require_config(settings)

    expected_state = request.session.get('oauth_state')
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=400, detail='Invalid OAuth state')

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            'https://github.com/login/oauth/access_token',
            headers=_oauth_headers(),
            data={
                'client_id': settings.github_client_id,
                'client_secret': settings.github_client_secret,
                'code': code,
                'redirect_uri': settings.github_redirect_uri,
                'state': state,
            },
        )

        if token_response.status_code >= 400:
            raise HTTPException(status_code=502, detail='Failed to exchange OAuth token')

        token_data = token_response.json()
        access_token = token_data.get('access_token')
        if not access_token:
            raise HTTPException(status_code=502, detail='No access token returned by GitHub')

        user_response = await client.get(
            'https://api.github.com/user',
            headers=_oauth_headers(access_token),
        )
        if user_response.status_code >= 400:
            raise HTTPException(status_code=502, detail='Failed to fetch GitHub profile')

        user = user_response.json()

        email_response = await client.get(
            'https://api.github.com/user/emails',
            headers=_oauth_headers(access_token),
        )
        email = None
        if email_response.status_code < 400:
            emails = email_response.json()
            primary = next((e for e in emails if e.get('primary')), None)
            verified = next((e for e in emails if e.get('verified')), None)
            chosen = primary or verified or (emails[0] if emails else None)
            if chosen:
                email = chosen.get('email')

    session_user = {
        'id': user.get('id'),
        'login': user.get('login'),
        'name': user.get('name'),
        'avatar_url': user.get('avatar_url'),
        'profile_url': user.get('html_url'),
        'email': email,
    }
    request.session['user'] = session_user
    request.session.pop('oauth_state', None)

    return {'message': 'Authentication successful', 'user': session_user}


@app.get('/me')
async def me(request: Request) -> dict[str, Any]:
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail='Not authenticated')
    return {'authenticated': True, 'user': user}


@app.post('/logout')
async def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {'message': 'Logged out'}
