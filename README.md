# GitHub Auth Service (FastAPI)

This is a standalone FastAPI service for GitHub OAuth login.

## 1) Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2) Configure environment

Copy `.env.example` to `.env` and set values:

- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `GITHUB_REDIRECT_URI` (must match your GitHub OAuth app callback URL)
- `SECRET_KEY`
- `SESSION_HTTPS_ONLY`

On GitHub, create an OAuth app:

- Homepage URL: `http://127.0.0.1:8000`
- Authorization callback URL: `http://127.0.0.1:8000/auth/callback`

## 3) Run

```bash
uvicorn app.main:app --reload --port 8000 --env-file .env
```

## 4) Endpoints

- `GET /health` - health check
- `GET /login` - returns JSON (user if already authenticated, otherwise authorization URL); use `?redirect=true` for redirect flow
- `GET /auth/callback` - GitHub callback route
- `GET /me` - current authenticated session user
- `POST /logout` - clear session
