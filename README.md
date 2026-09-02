# Mimicron

Parent repository for the Mimicron backends. Each service lives in its own
repository and is tracked here as a git submodule.

| Path | Repository |
|---|---|
| `backend_auth` | [mimicron_auth_be](https://github.com/rock4ts/mimicron_auth_be) — JWT identity, users, Yandex OAuth |
| `backend_content` | [mimicron_content_be](https://github.com/rock4ts/mimicron_content_be) — AI companion API, protected by auth-service JWTs |

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
```

Then:

```bash
docker compose up --build
```

Compose starts a dedicated PostgreSQL for each backend, plus Redis for auth,
then runs Alembic migrations. Both APIs verify JWTs with the same RS256
public key from `backend_auth/tests/docker/certs`.

Published host ports are for local diagnostics only. Production should expose
only a future Next.js origin / ingress, not `:8000` / `:8001`.

| Service | Direct URL | Gateway prefix (`ROOT_PATH`) |
|---|---|---|
| Auth API | <http://localhost:8000> | `/auth/api` |
| Auth Swagger | <http://localhost:8000/docs> | `/auth/api` |
| Content API | <http://localhost:8001> | `/content/api` |
| Content Swagger | <http://localhost:8001/docs> | `/content/api` |

`ROOT_PATH` only changes OpenAPI/Swagger public URLs. Route matching stays at
the bare paths (`/health`, `/token`, `/companions`, …). A future proxy must
strip `/auth/api` and `/content/api` before forwarding.

PostgreSQL and Redis stay on the Compose network and are not published to the host.

```bash
docker compose exec postgres_auth psql -U admin -d auth
docker compose exec postgres_content psql -U admin -d mimicron
```

Stop:

```bash
docker compose down
```

## Future frontend / BFF

The browser should talk to one origin. A future Next.js BFF will:

1. Call auth server-to-server (`POST /token`, `POST /refresh`, Yandex start/callback).
2. Keep access JWTs and refresh tokens out of browser JavaScript.
3. Forward auth `Set-Cookie` values (`refresh`, `device_id`, OAuth `state`) as
   first-party cookies on the app domain.
4. Call content with `Authorization: Bearer <access>`.
5. Forward `x-request-id` on every backend request.
6. Use a long read timeout on `POST /conversations/{id}/messages` (LLM default
   timeout is 60 seconds).

Do not add CORS to the Python APIs. Yandex `YANDEXID_REDIRECT_URL` stays on the
auth service until the Next.js callback exists.

## Layout

- `backend_auth/` — Auth API. See [`backend_auth/README.md`](backend_auth/README.md).
- `backend_content/` — Content API. See [`backend_content/README.md`](backend_content/README.md).
- `docker-compose.yml` — parent Compose file for a shared local environment.
- `envs/` — local environment files; not committed. Examples: `envs/*.example`.
