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

## Layout

- `backend_auth/` — Auth API. See [`backend_auth/README.md`](backend_auth/README.md).
- `backend_content/` — Content API. See [`backend_content/README.md`](backend_content/README.md).
- `docker-compose.yml` — parent Compose file (not yet populated).
- `envs/` — local environment files; not committed.
