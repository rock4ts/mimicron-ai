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

| Service | URL |
|---|---|
| Auth API | <http://localhost:8000> |
| Auth Swagger | <http://localhost:8000/docs> |
| Content API | <http://localhost:8001> |
| Content Swagger | <http://localhost:8001/docs> |

PostgreSQL and Redis stay on the Compose network and are not published to the host.

```bash
docker compose exec postgres_auth psql -U admin -d auth
docker compose exec postgres_content psql -U admin -d mimicron
```

Stop:

```bash
docker compose down
```

## Layout

- `backend_auth/` — Auth API. See [`backend_auth/README.md`](backend_auth/README.md).
- `backend_content/` — Content API. See [`backend_content/README.md`](backend_content/README.md).
- `docker-compose.yml` — parent Compose file for a shared local environment.
- `envs/` — local environment files; not committed. Examples: `envs/*.example`.
