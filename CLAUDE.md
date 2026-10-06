# CLAUDE.md

Uptime-монитор «Pulse» (тестовое задание MadDevs). Полный контракт домена и
API — `docs/CONTRACT.md` (источник правды), решения — `docs/DECISIONS.md`.

## Команды

- `make up` — поднять стек (Docker Compose; фронт :8080, api :8000,
  эмулятор :8090, postgres :15432).
- `make test` — pytest в контейнерах (профиль `test`, отдельная test-БД).
- `make seed-history` — синтетика для перф-проверок истории.
- Backend локально: `cd backend && uv sync && uv run pytest` (DB-тесты
  skipped без TEST_DATABASE_URL). Линтер: `uv run ruff check app tests scripts`.
- Frontend локально: `cd frontend && npm install && npm run dev` (проксирует
  /api на :8000).

## Соглашения

- Время — только UTC (`app.db.utcnow`); фронтенд конвертирует при показе.
- Логика инцидентов — чистые функции в `app/checks/logic.py`; меняя
  поведение, обнови CONTRACT.md §3 + DECISIONS.md + тесты.
- Шедулер диспатчит `CheckJob` (примитивы), не ORM-инстансы — иначе merge
  затирает конкурентные апдейты колонок (см. fix от 2026-10-05).
- Dockerfile backend: стейджи builder → runtime → test; сервисы compose
  обязаны пиновать `target: runtime`.
- Дизайн-токены фронта — hex-значения из CONTRACT.md §9 (проверены
  валидатором dataviz-скилла); статусные цвета всегда с подписью.
