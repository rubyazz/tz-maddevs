# CONTRACT — Pulse

Источник правды для backend/frontend/тестов. Расхождение с ним — баг.
Схема БД canonically живёт в `backend/app/models.py` + миграции
`alembic/versions/0001_initial.py`; ниже — только правила.

## Архитектура

frontend (nginx :8080, SPA + прокси /api) → api (FastAPI :8000) ⇄ PostgreSQL 16
(хост :15432) · Redis 7 (pub/sub события, leader-lock) · scheduler (тот же
образ, `python -m app.scheduler`) · demo-sites (:8090). Публичная страница —
без auth.

## Доменные правила (ядро корректности)

1. **Проверка**: GET url, timeout=timeout_seconds, follow_redirects.
   Успех = код == expected_status И (expected_body null ИЛИ подстрока в теле).
   Всё остальное — неудача с человекочитаемым error; response_time_ms — всегда.
2. **Claim**: перед выполнением атомарно
   `UPDATE checks SET in_flight_until = now()+timeout+10s WHERE id=? AND paused=false
   AND (in_flight_until IS NULL OR in_flight_until<=now()) RETURNING *`;
   0 строк → пропуск. После — NULL. Работает между процессами, самолечится.
3. **Результат (одна транзакция)**: insert check_results; обновить last_*;
   неудача: failures+1, при 1-й — failing_since=now; успех: failures=0.
   state='down' при failures≥threshold, 'up' на успехе. Инциденты:
   - нет открытого и порог достигнут → создать (started_at=failing_since);
     не в окне → DOWN-письмо (notified_down_at), иначе suppressed-строка;
   - открытый и notified_down_at IS NULL и не в окне → DOWN-письмо
     (путь «окно кончилось, сайт лежит»);
   - открытый и успех → закрыть (ended_at); не в окне → UP-письмо.
   Событие `check.update` (+`incident.opened/closed`) в Redis pub/sub.
4. **Окно обслуживания** (на проверку ИЛИ группу): проверки идут,
   инциденты пишутся, письма suppressed. Проход шедулера каждые ~5с:
   открытые инциденты с notified_down_at IS NULL и уже не в окне → DOWN.
5. **Шедулер**: тик 1с; due = `not paused AND next_run_at<=now`; claim
   одновременно ставит `next_run_at = now + interval` (слоты не
   навёрстываются, самопараллельность исключена). Пауза — не выбирается;
   резюм — next_run_at=now. Рестарт — расписание из БД; простой = дыра.
   Leader-lock Redis (потеря — немедленный exit). Суточно: чистка
   результатов старше RESULTS_RETENTION_DAYS (90).
6. **Статус группы** (вычисляемый, по непаузенным): есть down → major если
   все, иначе partial; иначе unknown → degraded, иначе operational.
7. **История**: date_bin-бакеты: day→5м, week→1ч, month→6ч. Бакет: count,
   ok_count, uptime_ratio (null при 0), avg/max response_ms. Дыры = count 0.
8. **Письма**: адреса = alert_emails группы (нет адресов → noreply@pulse.local
   с пометкой). Тема `[Pulse] DOWN|UP: {name}`. Транспорт: SMTP_HOST задан →
   aiosmtplib, иначе статус sent в outbox.

## API (`/api`, Bearer JWT; чужое = 404; даты ISO 8601 UTC)

| Метод и путь | Назначение |
|---|---|
| POST /auth/register, /auth/login | {token, user}; GET /me |
| GET /overview | группы + статус + checks + alert_emails (снапшот дашборда) |
| POST/GET /groups; PATCH/DELETE /groups/{id} | public_slug: null=снять, строка 3–64 [a-z0-9-] (409 при занятости) |
| POST/DELETE /groups/{id}/emails[/{email_id}] | адреса оповещений; POST …/emails/{id}/test — тестовое письмо |
| POST /groups/{id}/public-slug/generate | негадаемый slug |
| POST/GET /checks; GET/PATCH/DELETE /checks/{id} | валидация: interval 30–3600, timeout 1–30, threshold 1–10; PATCH paused=false → next_run_at=now |
| POST /checks/{id}/run · /pause · /resume | ручной запуск (409 если пауза/уже выполняется) |
| GET /checks/{id}/history?period=day\|week\|month | §7 + summary (uptime, avg, p95) + инциденты периода |
| GET /checks/{id}/results?limit≤200&before= | сырые результаты, курсорная пагинация |
| GET/POST/PATCH/DELETE /maintenance-windows | ровно одна цель (check_id XOR group_id), ends>starts, tz-aware |
| GET /mailbox?limit | outbox (sent/suppressed + причина) |
| GET /events?token= | SSE (см. ниже) |
| GET /public/{slug} · /public/{slug}/events | публичная страница: только show_on_public проверки группы |
| GET /health | ok + scheduler_heartbeat |

## SSE

`retry: 3000`, heartbeat `: ping` каждые 15с. События `check.update`,
`incident.opened`, `incident.closed`; payload включает owner_id,
show_on_public, public_slug. `/api/events` фильтрует по владельцу токена,
публичный поток — по slug + show_on_public. Клиент на любое событие
инвалидирует queries (overview/check/history/results/mailbox/public).

## demo-sites (:8090, CORS *)

`GET /site/{name}` — ответ по режиму; `POST /mode/{name}` {mode, delay_ms}
— ok|error|dead(висит)|slow|flaky(каждый 2-й 500); `GET /modes`;
удобные `/ok /error /hang /slow/{ms} /flaky/{n}`. Состояние в памяти.

## Env

`DATABASE_URL, REDIS_URL, JWT_SECRET, SEED_DEMO, CORS_ORIGINS,
SMTP_HOST/PORT/USER/PASSWORD/MAIL_FROM (пусто = эмуляция),
RESULTS_RETENTION_DAYS=90, SCHEDULER_TICK_SECONDS=1, LOG_LEVEL` — см.
`app/config.py`.

## Seed (SEED_DEMO=1, идемпотентно)

demo@pulse.dev/demo1234 · Production (slug demo-status, email):
Main site (60с/10с/порог 3, public), Slow API (60с/5с/2, public, slow
3000мс), Flaky endpoint (30с/10с/3) · Internal: Legacy service (60с/10с/3)
· окно на Internal завтра 02:00–04:00 UTC · режимы эмулятора: все ok.

## Дизайн-токены (проверены валидатором dataviz)

Фон #020617 · поверхность #0f172a · рамка rgba(255,255,255,0.08) ·
ink #f1f5f9/#94a3b8/#64748b · gridline #1e293b · ось #334155 ·
статусы: up #0ca30c, down #d03b3b, paused #fab219, unknown #64748b,
info/обслуживание #3987e5 · серия линии #3987e5 · availability-бары:
1→#0ca30c, <1→#ec835a, 0→#d03b3b, дыра→пусто.
Правила: статусный цвет всегда с подписью; текст — только ink-токены;
одна серия — без легенды; двух осей нет (линия и полоса — два графика);
тултипы обязательны; tabular-nums в таблицах/тиках; линия 2px, бары ≤24px
с 2px зазором; дыры рвут линию (connectNulls=false).
