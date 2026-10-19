# Auth API

Сервис идентификации: JWT-вход, учётные записи пользователей, OAuth через Яндекс ID и история входов в PostgreSQL.

## Требования

- Docker и Docker Compose.
- [uv](https://docs.astral.sh/uv/) — менеджер окружения и зависимостей. Python 3.12
  зафиксирован в `.python-version`.
- [just](https://github.com/casey/just) — для запуска тестов.
- Пара ключей RS256 в `certs/jwt-private.pem` и `certs/jwt-public.pem` для локального запуска.
  Тестовые ключи лежат в `tests/docker/certs/`.

Зависимости перечислены в `pyproject.toml`; точные версии — в `uv.lock`.

## Конфигурация

```bash
cp .env.example .env
```

Основные настройки:

- `POSTGRES_DB` — имя базы PostgreSQL
- `POSTGRES_USER` — пользователь PostgreSQL
- `POSTGRES_PASSWORD` — пароль PostgreSQL
- `POSTGRES_HOST` — хост PostgreSQL
- `POSTGRES_PORT` — порт PostgreSQL
- `REDIS_HOST` / `REDIS_PORT` — Redis для чёрного списка refresh-токенов и ограничения частоты запросов
- `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` — PEM-файлы RS256
- `YANDEXID_CLIENT_ID` / `YANDEXID_CLIENT_SECRET` — учётные данные Yandex OAuth
- `YANDEXID_REDIRECT_URL` — callback URL, который зарегистрирован в Yandex OAuth
- `ROOT_PATH` — публичный префикс за gateway (например `/auth/api`); для прямого локального запуска оставляйте пустым
- `REQUEST_ID_HEADER` — заголовок корреляции, по умолчанию `x-request-id`
- `PROD_RUN` — включает флаг `Secure` у cookies
- `LOG_LEVEL` — уровень логирования

Настройки загружаются через Pydantic из `app/config.py`.

## Архитектура

Каждый HTTP-запрос получает Unit of Work (`UnitOfWork`) с сессией SQLAlchemy.
Репозитории принимают UoW и работают с базой через `uow.session` (add/flush/запросы),
но не делают commit. Сервисы принимают репозитории (и Redis, если нужно) и фиксируют
изменения через `repository.uow.commit()`.

Access-токены — это JWT с алгоритмом RS256. Claims: `sub`, `is_superuser`, `tv` (версия токена),
`type`, `iat`, `exp`, `jti`. Access-токен возвращается в JSON `{"access": "<jwt>"}`.
Refresh-токен ротируется при каждом `POST /refresh` (старый `jti` попадает в Redis blacklist)
и хранится только в cookie `refresh`.

Cookies `refresh`, `device_id` и OAuth `state` выставляются с `HttpOnly`, `SameSite=Lax`,
`Path=/`, без `Domain`. Флаг `Secure` включается при `PROD_RUN=true`. Удаление cookies
использует те же атрибуты `Path`/`Domain`.

Yandex OAuth: `GET /yandexid/login` ставит cookie `state` и редиректит на провайдера с PKCE.
Verifier хранится в Redis и потребляется один раз. Client secret используется только в
server-side обмене кода на токен (`POST` на token URL), а не в ответе браузеру.
`GET /yandexid/token` сверяет query `state` с cookie и Redis, затем выдаёт access JWT и
ставит cookies `refresh` / `device_id`.

Будущий same-origin BFF вызывает эти эндпоинты server-to-server: забирает
`access` из JSON и складывает cookies `refresh` / `device_id` / `state` в
серверную Redis-сессию. Браузер получает только непрозрачную session-cookie BFF
и никогда не видит access/refresh JWT. Callback Yandex указывает на
`{APP_ORIGIN}/api/auth/yandex/callback`; то же значение должно быть в
`YANDEXID_REDIRECT_URL` и в настройках приложения Яндекса.

## Запуск в Docker

Положите JWT-ключи в `certs/` (или скопируйте `tests/docker/certs/`), затем:

```bash
docker compose up --build
```

Образ собирается через uv из `uv.lock`. После того как PostgreSQL станет healthy, бэкенд
применяет миграции Alembic и доступен по адресу <http://localhost:8000>.
Swagger UI: <http://localhost:8000/docs>.

```bash
docker compose down
```

## Локальный запуск

```bash
uv sync
```

Запустите PostgreSQL и Redis, затем:

```bash
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Новые миграции: `uv run alembic revision -m "описание"`. Имена файлов начинаются
с даты и времени (`YYYY_MM_DD_HHMM_SS`).

Необязательный суперпользователь после миграции:

```bash
uv run python -m app.commands.create_superuser --email admin@example.com --password password
```

Добавление зависимостей:

```bash
uv add <package>
uv add --group dev <package>
```

После изменения `pyproject.toml`:

```bash
uv lock
```

## Тесты

Тесты используют отдельный `docker-compose.tests.yml` с изолированными PostgreSQL, Redis,
моком Yandex OAuth, тестовым бэкендом и pytest-раннером. `Dockerfile.tests-app`
устанавливает зависимости приложения и запускает API. `Dockerfile.tests` устанавливает
зависимости приложения и группы `test`, затем запускает pytest. Оба контейнера загружают `.env.tests`.
Pytest читает `TEST_BASE_URL`, `POSTGRES_*`, `REDIS_*` и `YANDEX_MOCK_URL` через
Pydantic Settings в `tests/functional/settings.py`. Тесты стартуют после миграций Alembic
и успешного healthcheck бэкенда.

```bash
just run-tests
```

Команда поднимает тестовый стек, запускает pytest и всегда выполняет
`docker compose -f docker-compose.tests.yml down -v`, в том числе при ошибке.

## Линтинг

```bash
uv run ruff format --check .
uv run ruff check .
```

Автоформатирование:

```bash
uv run ruff format .
```

## CI

GitHub Actions (`.github/workflows/auth-api-pep.yml`) запускает проверку стиля
и функциональные тесты в Docker на pull request и push. После ruff и тестов
workflow отправляет уведомление в Telegram независимо от успеха или ошибки
(не при отмене запуска): для этого в секретах репозитория нужны
`TELEGRAM_CHAT_ID` и `TELEGRAM_BOT_TOKEN`.

## API

- `GET /` — редирект на `/docs`
- `GET /health`
- `POST /token` — вход по email и паролю
- `POST /refresh` — новый access-токен по refresh-cookie
- `POST /logout` — отзыв текущего refresh-токена
- `POST /logout-others` — отзыв остальных сессий (Bearer-токен)
- `POST /users` — регистрация
- `GET /users/me` — текущий пользователь (Bearer-токен)
- `PATCH /users/me/email`
- `PATCH /users/me/password`
- `GET /users/me/login-history`
- `GET /yandexid/login` — редирект на Yandex OAuth
- `GET /yandexid/token` — OAuth callback
