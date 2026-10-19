# Mimicron

Монорепозиторий сервисов Mimicron.

| Путь | Назначение |
|---|---|
| `backend_auth` | JWT-идентичность, пользователи, Yandex OAuth |
| `backend_content` | API AI-компаньона, извлечение долгосрочной памяти из диалогов, сверка дубликатов и обновлений, хранение в PostgreSQL, векторный индекс в Qdrant и семантический поиск релевантных воспоминаний при ответе, защищён JWT сервиса авторизации |
| `frontend` | UI на Next.js и BFF |

## Клонирование

```bash
git clone <repo-url>
cd mimicron-ai
```

## Запуск стека

Скопируйте примеры env-файлов и заполните секреты (`LLM_API_KEY`, Yandex OAuth):

```bash
cp envs/auth.env.example envs/auth.env
cp envs/content.env.example envs/content.env
cp envs/frontend.env.example envs/frontend.env
```

Затем:

```bash
docker compose up --build
```

Compose поднимает отдельный PostgreSQL для каждого бэкенда, Redis для auth,
Redis для сессий BFF, Qdrant для векторного индекса воспоминаний, затем запускает
миграции Alembic и Next.js BFF.

Браузерный origin — <http://localhost:3000>. Auth `:8000` и content `:8001`
нужны только для локальной диагностики и не должны быть опубликованы в
продакшене.

| Сервис | Прямой URL | Префикс шлюза (`ROOT_PATH`) |
|---|---|---|
| Frontend / BFF | <http://localhost:3000> | — |
| Auth API | <http://localhost:8000> | `/auth/api` |
| Auth Swagger | <http://localhost:8000/docs> | `/auth/api` |
| Content API | <http://localhost:8001> | `/content/api` |
| Content Swagger | <http://localhost:8001/docs> | `/content/api` |

`ROOT_PATH` меняет только публичные URL OpenAPI/Swagger. Сопоставление маршрутов
остаётся по «голым» путям (`/health`, `/token`, `/companions`, …). BFF вызывает
внутренние URL вида `http://backend_auth:8000/token` — никогда `/auth/api` или
`/content/api`.

PostgreSQL, Redis и Qdrant остаются в сети Compose и не публикуются на хост.

```bash
docker compose exec postgres_auth psql -U admin -d auth
docker compose exec postgres_content psql -U admin -d mimicron
```

Остановка:

```bash
docker compose down
```

## Контракт Frontend / BFF

Браузер общается с одним origin (Next.js). Next.js:

1. Вызывает auth server-to-server (`POST /token`, `POST /refresh`, старт/callback Yandex).
2. Хранит access JWT и auth-cookie (`refresh`, `device_id`, OAuth `state`) в
   выделенной Redis-сессии. Браузер получает только непрозрачную `HttpOnly`
   cookie сессии (`mimicron-session` локально, `__Host-mimicron-session` в
   продакшене).
3. Никогда не отдаёт access- или refresh-токены в JavaScript браузера.
4. Вызывает content с заголовком `Authorization: Bearer <access>`.
5. Пробрасывает `x-request-id` в каждый запрос к бэкенду.
6. Использует длинный read timeout на `POST /conversations/{id}/messages`
   (таймаут LLM по умолчанию — 60 секунд; у BFF — 70 секунд). Первая реплика
   может включать второй нефатальный вызов LLM для названия диалога.
7. Требует `Origin` и `x-csrf: 1` на мутирующих запросах `/api/*`.

Не добавляйте CORS в Python API. Зарегистрируйте Yandex
`YANDEXID_REDIRECT_URL` как `http://localhost:3000/api/auth/yandex/callback`
(или продакшен-эквивалент).

Локальное ограничение частоты запросов auth видит адрес BFF, если доверенный
ingress не выставил `TRUST_PROXY_HEADERS` / `TRUSTED_PROXY_IPS` и флаг BFF
`TRUST_PROXY`.

## CI

GitHub Actions (`.github/workflows/`) запускаются условно при изменениях в соответствующих сервисах или общем окружении:

- `.github/workflows/auth-api-pep.yml` — ruff и функциональные тесты `backend_auth` в Docker при изменениях в `backend_auth/**`.
- `.github/workflows/content-api-pep.yml` — ruff и функциональные тесты `backend_content` в Docker при изменениях в `backend_content/**`.
- `.github/workflows/frontend-ci.yml` — lint, unit-тесты, сборка, typecheck и Playwright для `frontend` при изменениях в `frontend/**`.
- `.github/workflows/stack-smoke.yml` — проверка `docker compose config` при изменениях Compose, примеров env, smoke-скриптов или сервисов.

После успешного или неуспешного прогона каждый workflow отправляет сообщение в Telegram (не при отмене запуска); добавьте `TELEGRAM_CHAT_ID` и `TELEGRAM_BOT_TOKEN` как секреты репозитория.

## Структура

- `backend_auth/` — Auth API. См. [`backend_auth/README.md`](backend_auth/README.md).
- `backend_content/` — Content API. См. [`backend_content/README.md`](backend_content/README.md).
- `frontend/` — UI на Next.js и BFF. См. [`frontend/README.md`](frontend/README.md).
- `docker-compose.yml` — родительский Compose-файл для общего локального окружения.
- `envs/` — локальные файлы окружения; не коммитятся. Примеры: `envs/*.example`.
