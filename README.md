# Mimicron

Parent repository for Mimicron services. Each service lives in its own
repository and is tracked here as a git submodule.

| Path | Repository |
|---|---|
| `backend_auth` | [mimicron_auth_be](https://github.com/rock4ts/mimicron_auth_be) — JWT identity, users, Yandex OAuth |
| `backend_content` | [mimicron_content_be](https://github.com/rock4ts/mimicron_content_be) — AI companion API, protected by auth-service JWTs |
| `frontend` | [mimicron_fe](https://github.com/rock4ts/mimicron_fe) — Next.js UI and BFF |

## Clone

```bash
git clone --recurse-submodules <parent-url>
```

If you already cloned without submodules:

```bash
git submodule update --init
```

## Run the stack

Copy the example env files and fill in secrets (`LLM_API_KEY`, Yandex OAuth):

```bash
cp envs/auth.env.example envs/auth.env
cp envs/content.env.example envs/content.env
cp envs/frontend.env.example envs/frontend.env
```

Then:

```bash
docker compose up --build
```

Compose starts a dedicated PostgreSQL for each backend, Redis for auth, Redis
for BFF sessions, then runs Alembic migrations and the Next.js BFF.

The browser origin is <http://localhost:3000>. Auth `:8000` and content `:8001`
are local diagnostics only and should not be published in production.

| Service | Direct URL | Gateway prefix (`ROOT_PATH`) |
|---|---|---|
| Frontend / BFF | <http://localhost:3000> | — |
| Auth API | <http://localhost:8000> | `/auth/api` |
| Auth Swagger | <http://localhost:8000/docs> | `/auth/api` |
| Content API | <http://localhost:8001> | `/content/api` |
| Content Swagger | <http://localhost:8001/docs> | `/content/api` |

`ROOT_PATH` only changes OpenAPI/Swagger public URLs. Route matching stays at
the bare paths (`/health`, `/token`, `/companions`, …). The BFF calls internal
URLs such as `http://backend_auth:8000/token` — never `/auth/api` or
`/content/api`.

PostgreSQL and both Redis instances stay on the Compose network and are not
published to the host.

```bash
docker compose exec postgres_auth psql -U admin -d auth
docker compose exec postgres_content psql -U admin -d mimicron
```

Stop:

```bash
docker compose down
```

## Frontend / BFF contract

The browser talks to one origin (Next.js). Next.js:

1. Calls auth server-to-server (`POST /token`, `POST /refresh`, Yandex start/callback).
2. Stores access JWTs and auth cookies (`refresh`, `device_id`, OAuth `state`) in
   a dedicated Redis session. The browser receives only an opaque `HttpOnly`
   session cookie (`mimicron-session` locally, `__Host-mimicron-session` in
   production).
3. Never returns access or refresh tokens to browser JavaScript.
4. Calls content with `Authorization: Bearer <access>`.
5. Forwards `x-request-id` on every backend request.
6. Uses a long read timeout on `POST /conversations/{id}/messages` (LLM default
   timeout is 60 seconds; BFF default is 70 seconds).
7. Requires `Origin` plus `x-csrf: 1` on mutating `/api/*` requests.

Do not add CORS to the Python APIs. Register Yandex
`YANDEXID_REDIRECT_URL` as `http://localhost:3000/api/auth/yandex/callback`
(or the production equivalent).

Local auth rate limiting sees the BFF address unless a trusted ingress sets
`TRUST_PROXY_HEADERS` / `TRUSTED_PROXY_IPS` and the BFF `TRUST_PROXY` flag.

## CI

GitHub Actions (`.github/workflows/stack-smoke.yml`) checks `docker compose config`
on pull request and push to `main` when Compose, env examples, smoke scripts, or
frontend files change. On success the workflow sends a Telegram message; add
`TELEGRAM_CHAT_ID` and `TELEGRAM_BOT_TOKEN` as repository secrets.

## Layout

- `backend_auth/` — Auth API. See [`backend_auth/README.md`](backend_auth/README.md).
- `backend_content/` — Content API. See [`backend_content/README.md`](backend_content/README.md).
- `frontend/` — Next.js UI and BFF. See [`frontend/README.md`](frontend/README.md).
- `docker-compose.yml` — parent Compose file for a shared local environment.
- `envs/` — local environment files; not committed. Examples: `envs/*.example`.
