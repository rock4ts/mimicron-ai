# Mimicron frontend / BFF

Same-origin Next.js App Router app. The browser talks only to this origin. Access
and refresh JWTs stay in a Redis session; the browser receives one opaque
`HttpOnly` session cookie.

## Design

Visual design and page layouts follow the legacy FastAPI templates and CSS in
`backend_content/app/templates` and `backend_content/app/static/css/main.css`
(dashboard, companion detail, and full-page chat). That HTML is a design
reference only: this app does not use HTMX, does not call `/ui/*` routes, and
does not render backend HTML error pages. Navigation, forms, and chat stay on
Next.js routes and `/api/*` BFF handlers.

The UI is Russian-only. Frontend-owned labels, validation, and fallback
messages are in Russian; error details returned by Auth API or Content API are
passed through unchanged and may use another language. Conversation history
shows an LLM-generated Russian title after the first reply; until then the
fallback is `Диалог {datetime}`.

## Requirements

- Node.js 24 and [pnpm](https://pnpm.io/)
- Redis for BFF sessions
- Auth API and Content API on the private network

## Configuration

```bash
cp .env.example .env
```

| Variable                 | Purpose                                                                                                                                                                             |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AUTH_INTERNAL_URL`      | Bare auth origin, e.g. `http://backend_auth:8000`                                                                                                                                   |
| `CONTENT_INTERNAL_URL`   | Bare content origin, e.g. `http://backend_content:8000`                                                                                                                             |
| `REDIS_URL`              | Dedicated BFF Redis                                                                                                                                                                 |
| `APP_ORIGIN`             | Browser origin used for CSRF and OAuth redirects. Comma-separate localhost aliases if needed                                                                                        |
| `REQUEST_ID_HEADER`      | Correlation header, default `x-request-id`                                                                                                                                          |
| `BFF_MESSAGE_TIMEOUT_MS` | Timeout for `POST /conversations/{id}/messages`, default `70000`. The first reply may wait on a second LLM call that names the conversation; title failure does not fail the reply. |
| `PROD_RUN`               | Enables `Secure` and `__Host-` session cookie                                                                                                                                       |
| `TRUST_PROXY`            | Forward `X-Forwarded-For` only when a trusted ingress is configured                                                                                                                 |

Do not call Python APIs from the browser. Do not add CORS to the backends.

Yandex callback (register this exact URL with Yandex):

```text
{APP_ORIGIN}/api/auth/yandex/callback
```

Auth `YANDEXID_REDIRECT_URL` must match. The BFF stores auth `refresh`,
`device_id`, and OAuth `state` cookies in Redis; they are not forwarded to the
browser.

Mutating `/api/*` requests must send `Origin` matching `APP_ORIGIN` and
`x-csrf: 1`.

## Scripts

```bash
pnpm dev
pnpm test
pnpm build
pnpm start
pnpm test:e2e
```

Playwright expects Redis on `REDIS_URL` and a production build. After
installing or upgrading Playwright, download browsers once:

```bash
pnpm exec playwright install chromium
```

By default Playwright reuses whatever is already listening on port 3000
(including `docker compose`). To run against a fresh local build instead:

```bash
pnpm build
PLAYWRIGHT_PORT=3010 pnpm test:e2e
```

## CI

GitHub Actions (`.github/workflows/frontend-ci.yml`) runs lint, unit tests, typecheck,
build, and Playwright on pull request and push to `main`. After a successful or
failed run the workflow sends a Telegram message (not on cancelled runs); add
`TELEGRAM_CHAT_ID` and `TELEGRAM_BOT_TOKEN` as repository secrets.

## Docker

The production image uses Next.js `output: "standalone"` and listens on `:3000`.
Health: `GET /api/health`.
