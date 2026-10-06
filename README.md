# Pulse — монитор доступности сайтов

Клиент-серверный uptime-монитор (тестовое задание MadDevs): пользователь
добавляет сайты, сервис проверяет их по расписанию, показывает статусы в
реальном времени и шлёт письма о падениях/восстановлениях.

**Стек:** FastAPI + SQLAlchemy 2 async + Alembic + PostgreSQL 16 + Redis
(pub/sub, SSE) · шедулер — отдельный asyncio-процесс · React 18 + TS +
Vite + TanStack Query + Tailwind + Recharts · Docker Compose · почта
эмулируется (outbox в БД + страница «Mailbox»; реальный SMTP — опционально
через env).

Документы: [CONTRACT](docs/CONTRACT.md) · [DECISIONS](docs/DECISIONS.md) ·
[PROMPTS](docs/PROMPTS.md) · [STATE](docs/STATE.md) · [PROOF](docs/PROOF.md)

## Быстрый старт

Нужен только Docker (engine + compose v2).

```bash
cp .env.example .env
docker compose up -d --build   # первая сборка ~минута
```

| Что | Где |
|---|---|
| Приложение | http://localhost:8080 |
| Демо-вход | `demo@pulse.dev` / `demo1234` (предзаполнен) |
| API docs | http://localhost:8000/docs |
| Публичная страница | http://localhost:8080/status/demo-status |
| Эмулятор сайтов | http://localhost:8090/docs |
| Postgres | `localhost:15432`, `pulse/pulse` |

Останов: `docker compose down`; сброс с данными: `make clean`.

## Демо за 5 минут

1. **Demo** → переключите `main` в `error`.
2. **Dashboard** → у «Main site» жмите ⚡ Run now трижды (порог 3): статус
   Down, в **Mailbox** — письмо DOWN.
3. Ещё сколько угодно Run now — писем больше нет.
4. `main` → `ok`, Run now: статус Up, письмо UP.
5. **Maintenance**: окно на группу Production «на сейчас»; уроните `main`,
   3× Run now → инцидент есть, письмо suppressed; закройте окно — письмо
   DOWN уйдёт само за ~5с.
6. Откройте `/status/demo-status` во второй вкладке — статусы меняются сами.
7. `docker compose restart api scheduler` — проверки продолжаются, простой
   виден дырой в истории.

Подробные сценарии с выводами — [PROOF.md](docs/PROOF.md).

## Разработка

```bash
make test           # pytest в контейнерах (unit + integration)
make seed-history   # ~85K синтетических результатов на проверку (перф-пруф)
make logs
```

Backend локально: `cd backend && uv sync && uv run pytest` · линтер:
`uv run ruff check app tests scripts`.
Frontend: `cd frontend && npm install && npm run dev` (проксирует /api).

Структура: `backend/` (api, checks, scheduler, alembic, tests) ·
`frontend/` (pages, components, api, lib) · `demo-sites/` (эмулятор) ·
`docs/`.
