# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Shokoladnitsa is a table booking system for a café, implemented as a **VK Mini App**. The frontend runs inside VK's iframe; the backend is a FastAPI service with a VK bot and task scheduler.

---

## Commands

### Backend (run from `backend/`)

```bash
# Activate venv first (Windows)
.venv\Scripts\activate

# Run API server only (port 8001)
python -m uvicorn app.main:app --reload --port 8001

# Run all services (API + VK Long Poll bot + scheduler)
python start_all.py

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_api.py -v

# Run a single test by name
pytest tests/test_api.py::test_create_reservation -v

# Alembic migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Frontend (run from `vk-table-booking/`)

```bash
npm run dev          # Vite dev server on port 5173 (proxies /api → :8001)
npm run build        # Production build
npm run lint         # ESLint

# Tunnel options for VK Mini App testing
npm run dev:tunnel      # ngrok tunnel
npm run dev:tunnel:cf   # cloudflared tunnel
npm run dev:tunnel:dt   # devtunnel
```

---

## Architecture

### Backend (`backend/`)

Three concurrent processes started via `start_all.py`:
1. **FastAPI** (`app/main.py`) — HTTP API on port 8001
2. **VK Long Poll bot** (`app/vk_bot_server.py`) — handles incoming VK messages
3. **Scheduler** (`app/scheduler.py`) — polls DB every 60s, executes due tasks

**Data flow for a new booking:**
`POST /api/reservation` → rate limit check (DB per-IP + in-memory global) → duplicate check (phone+date) → save `Reservation` → notify waiters VK chat → create `ScheduledTask` rows (confirmation, reminder if `vk_notifications`, feedback if `vk_notifications`) → return response.

**Scheduled task types** (`ScheduledTask.task_type`):
- `visit_confirmation` — at visit time, sends "did the guest arrive?" to waiters chat with inline keyboard
- `reminder` — 1 hour before, sends reminder to guest DM
- `feedback` — next day at 12:00, sends feedback request to guest DM

**Admin panel** (`app/admin/`):
- `stats.py` — aggregated booking statistics
- `charts.py` — matplotlib charts
- `export.py` — CSV export

### Frontend (`vk-table-booking/src/`)

- `App.jsx` — root: VK Bridge init, modal management, fetch with AbortController(10s)
- `pages/Home.jsx` — wraps `BookingForm` in VKUI `<Group>`
- `components/BookingForm.jsx` — form with VKUI inputs; on submit calls `onRequestConfirm({ payload, displayData })`
- `utils/validators.js` — client-side validation
- `index.css` — VKUI token overrides

**Confirm modal flow:** `BookingForm` → `onRequestConfirm` → `App.jsx` shows confirm modal → user clicks "Подтвердить" → `App.jsx` fetches API → on success increments `formResetKey` to unmount/remount form.

### Database (`backend/app/`)

Models (PostgreSQL via SQLAlchemy 2.0):
- `Reservation` — bookings; indexed on `(phone, date)` for duplicate checks
- `ScheduledTask` — deferred tasks; indexed on `(completed, scheduled_at)`
- `ErrorLog` — frontend + backend errors
- `RateLimitEntry` — per-IP rate limit (survives restarts)

**Two DB engines in `database.py`:**
- `engine` / `SessionLocal` (psycopg2, sync) — used by scheduler, vk_bot_server, admin panel
- `async_engine` / `AsyncSessionLocal` (asyncpg, async) — used by FastAPI endpoints via `get_db()`

Migrations live in `backend/migrations/` (Alembic). Run from `backend/` directory.

---

## Critical Rules

### VK Mini App — no CSP meta tag in index.html
Never add a `<meta http-equiv="Content-Security-Policy">` tag to `vk-table-booking/index.html`. VK manages the iframe CSP itself — adding one breaks VKUI fonts and causes the app to open as a standalone page instead of a Mini App. The backend `SecurityHeadersMiddleware` is fine (applies only to `/api/*` responses).

### VK Mini App — SecurityHeadersMiddleware must only apply to /api/*
`SecurityHeadersMiddleware` in `main.py` must guard with `if not request.url.path.startswith("/api/")`. If headers like `X-Frame-Options: SAMEORIGIN` or `Content-Security-Policy` are returned for non-API routes, they can break VK's iframe embedding of the app.

### Vite 7 — allowedHosts must be boolean true
`allowedHosts: ['all']` in `vite.config.js` does NOT work in Vite 7 — the string `'all'` is treated as a literal hostname.
Use `allowedHosts: true` (boolean) to allow all hosts (required when proxying through tunnels like ngrok).

### VK Mini App — popup behavior is by design
VK Mini Apps always open in VK's full content area (as a tab/page within the vk.com SPA). They do NOT open as floating popups. This is standard VK platform behavior, not a bug.

### Tunnel for mobile testing — use localtunnel
ngrok shows an interstitial page in WebView that blocks VK Bridge initialization on mobile (WebView has a separate cookie jar from the browser). Use localtunnel instead:
```bash
cd vk-table-booking
npm run dev:tunnel:lt    # lt --port 5173
```
URL format: `https://random-name.loca.lt` — no interstitial, works on mobile.

### Pydantic v2 — datetime field name collision
`date: date` and `time: time` clash with their type names in Pydantic v2.
Fix (already in `schemas.py`): `from datetime import date as Date, time as Time`, then use `Date`/`Time` as the type annotations.

### Tests — import order in conftest.py
`conftest.py` must call `load_dotenv()` **before** any `from app.*` imports, because `database.py` reads env vars at module level.

### Tests — rate limit reset
The global in-memory rate limit (`_global_log` list in `main.py`) must be cleared between tests. The `client` fixture in `conftest.py` does `_global_log.clear()`. The per-IP rate limit resets via `setup_database` (drops and recreates the `rate_limit` table).

### CORS
Whitelisted in `main.py`:
- `http://localhost:5173`, `https://localhost:5173`
- Regex: `*.ngrok-free.dev`, `*.loca.lt`, `*.trycloudflare.com`, `*.devtunnels.ms`

If adding a new tunnel domain, update `allow_origin_regex` in `main.py`.

### VKUI v7 — Div is deprecated
`<Div>` component from VKUI v7 is deprecated. Use `<Box>` instead (already fixed in `BookingForm.jsx`).

### VK Color Scheme
`App.jsx` reads `vk_color_scheme` from URL params and passes `appearance` to `<ConfigProvider>`. VK injects `?vk_color_scheme=space_gray` (dark) or `bright_light` (light) into the app URL.

### Async SQLAlchemy — two engines, not one
`database.py` exports both sync (`SessionLocal`) and async (`AsyncSessionLocal`) engines.
FastAPI `get_db()` yields `AsyncSession` (asyncpg). All DB queries in `main.py` use `await db.execute(select(...))`.
Scheduler and VK bot run in separate processes and use `SessionLocal` (sync, psycopg2).
Never use `db.query()` style in `main.py` — it's sync and will block the event loop.

### Async SQLAlchemy — count queries
In async mode, `db.query(Model).count()` does NOT work. Use:
```python
(await db.execute(select(func.count()).select_from(Model).where(...))).scalar()
```

### Sentry — optional, gated by env var
Both Python (`sentry-sdk`) and JS (`@sentry/react`) Sentry are optional.
Python: enabled only if `SENTRY_DSN` is set in `backend/.env`.
JS: enabled only if `VITE_SENTRY_DSN` is set in `vk-table-booking/.env`.
If DSN is missing, application runs normally without Sentry.

### Prometheus — /api/metrics/prometheus
`prometheus-fastapi-instrumentator` is mounted at startup.
Endpoint: `GET /api/metrics/prometheus` (Prometheus scrape format).
Does NOT conflict with the existing `GET /api/metrics` (JSON format).

### VKUI DateInput for date selection
`BookingForm.jsx` uses VKUI `DateInput` (not `<input type="date">`).
Value is converted: `dateStrToDate(str)` (YYYY-MM-DD → Date) for the component,
`dateToStr(date)` (Date → YYYY-MM-DD) in the `onDateChange` handler.
The YYYY-MM-DD string is kept internally in `form.date` for validators and payload.

### Error handling in App.jsx — retry for 5xx
`handleConfirmSubmit` retries automatically for statuses 500/502/503:
- Up to 3 attempts with delays 1s → 2s → 4s (exponential backoff via `retryCount` ref)
- After all retries exhausted: shows error modal with final message
- Network errors (AbortError, offline): shows error modal with "Попробовать снова" button

### VK API retry — temporary errors
`vk_api_call` in `vk_bot_server.py` retries VK API calls for temporary errors:
codes 1, 6, 9, 10 trigger up to `MAX_VK_RETRIES=3` retries with exponential backoff (1→2→4s).
Non-retryable errors (auth, permissions) fail immediately.

### Scheduler — daily summary at 9:00
`run_scheduler()` in `scheduler.py` sends a daily summary to the waiters chat at 9:00.
Uses `_last_summary_date` global to prevent duplicate sends on the same day.

---

## Environment

`backend/.env` (required keys):
```
DB_USER=postgres
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=5432
DB_NAME=reservation
VK_COMMUNITY_TOKEN=...
VK_GROUP_ID=...
VK_ADMIN_ID=...
VK_WAITERS_CHAT_ID=...
CAFE_ADDRESS=...
# Optional:
SENTRY_DSN=
APP_ENV=production
```

`vk-table-booking/.env` — Vite env vars (see `.env.example`):
```
VITE_VK_GROUP_ID=...
VITE_SENTRY_DSN=   # optional
```
