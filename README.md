# GitHub Auth Service (FastAPI)

This is a standalone FastAPI service for GitHub OAuth login.

## 1) Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2) Configure YAML

Copy `config.example.yaml` to `config.yaml` and set values:

- `github_client_id`
- `github_client_secret`
- `github_redirect_uri` (must match your GitHub OAuth app callback URL)
- `secret_key`
- `session_https_only`
- `postgres_dsn` (example: `host=localhost port=5432 dbname=postgres user=postgres password=xxxx connect_timeout=10 sslmode=prefer`)

On GitHub, create an OAuth app:

- Homepage URL: `http://127.0.0.1:8000`
- Authorization callback URL: `http://127.0.0.1:8000/auth/callback`

## 3) Run

```bash
uvicorn app.main:app --reload --port 8000
```

On startup, the app verifies PostgreSQL connectivity and prints:

```text
PostgreSQL connection successful (host=... port=... dbname=... user=...)
```

It also auto-creates auth tables if missing:
- `users`
- `roles`
- `user_roles`

On successful GitHub callback, only pre-provisioned users are allowed; user data is refreshed in `users` and the default `user` role is ensured in `user_roles`.
The `users` table stores only:
- `id` (GitHub user ID)
- `git_username` (GitHub login)
- `email`

Login access control:
- Admin pre-provisions users by `git_username`.
- Only users with a pre-provisioned `git_username` can login.
- On first successful login, `id` is filled from GitHub and `email` is refreshed.
- Startup seeds one admin user:
  - `id`: `250086117`
  - `git_username`: `kishormetapercept`
  - role: `admin` (and `user`)
- Any GitHub account not present in `users` is denied with `403`.

## 4) Endpoints

- `GET /health` - health check
- `GET /login` - returns JSON (user if already authenticated, otherwise authorization URL); use `?redirect=true` for redirect flow
- `POST /admin/register` - admin-only; register a user by `git_username`
- `GET /auth/callback` - GitHub callback route
- `GET /me` - current authenticated session user
- `POST /logout` - clear session

When using API gateway, call admin provisioning through:
- `POST http://127.0.0.1:9000/auth/admin/register`

`/admin/register` flow:
1. Check local DB first (`git_username` already present => `409 User is already registered`).
2. If not present, validate `git_username` with GitHub public API.
3. Validate provided `email` against GitHub public email for that username.
4. Insert into local DB only when both username and email are GitHub-verified.
