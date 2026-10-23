# Nexus One Authentication Service

Intern prototype for **Authentication & Token Management** (11 logics).

## Setup

PostgreSQL 15+ must be running. Docker:

```powershell
docker compose up -d
```

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Set a strong `JWT_SECRET` or `JWT_SECRET_KEY` (32+ characters) in `.env`. Never commit `.env`.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8090
```

- UI: http://127.0.0.1:8090/ui
- API docs: http://127.0.0.1:8090/docs

Do not use port 8000 if Nexus One is already using it.

## Endpoints

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | Public |
| POST | `/api/v1/auth/login` | Public |
| POST | `/api/v1/auth/refresh` | Refresh token |
| POST | `/api/v1/auth/logout` | Access token |
| POST | `/api/v1/auth/logout-all` | Access token |
| GET | `/api/v1/auth/me` | Access token |
| GET | `/api/v1/auth/sessions` | Access token |
| DELETE | `/api/v1/auth/sessions/{session_id}` | Access token |
| GET | `/protected` | Access token |

## Demo flow

1. `POST /api/v1/auth/login`
2. `GET /api/v1/auth/me` with `Authorization: Bearer <access_token>`
3. `POST /api/v1/auth/refresh` with `{ "refresh_token": "..." }`
4. `POST /api/v1/auth/logout` with the access token
5. Repeat `/me` and confirm `401 AUTH_TOKEN_REVOKED`

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest app/tests -q
```

## Token handling

- Access tokens are short-lived JWTs (`sub`, `user_id`, `roles`, `company_id`, `jti`, `iat`, `exp`, `token_type`).
- Refresh tokens are stored only as SHA-256 hashes in `auth_sessions`.
- Logout revokes the session and puts the access-token `jti` on `revoked_tokens`.
- Failed logins increment `failed_login_attempts` (five-failure lockout is out of scope).

One-page data flow: [ARCHITECTURE.md](ARCHITECTURE.md)

Security review form: [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)

## Example requests

Login:

```json
POST /api/v1/auth/login
{ "email": "intern.demo@casterly.com", "password": "ExamplePasswordOnly" }
```

Protected:

```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

Postman: import `postman_collection.json` and set `baseUrl` to `http://127.0.0.1:8090`.
