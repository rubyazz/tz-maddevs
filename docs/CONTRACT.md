# CONTRACT — Pulse, монитор доступности сайтов

Единственный источник правды для backend, frontend, тестов и инфраструктуры.
Расхождения с этим документом — баг. Изменения контракта — только через
обновление этого файла + запись в DECISIONS.md.

## 1. Архитектура

```
┌────────────┐   HTTP/JSON    ┌────────────┐    SQL     ┌────────────┐
│  frontend  │ ─────────────▶ │   api      │ ─────────▶ │ PostgreSQL │
│ (React/TS, │ ◀───────────── │ (FastAPI,  │            │    16      │
│  nginx)    │  SSE /events   │  uvicorn)  │            └────────────┘
└────────────┘                └─────┬──────┘
         │  /status/:slug  SSE            ▲ publish/subscribe (pub/sub)
         ▼                                │            ┌────────────┐
   ┌────────────┐        publish          │            │   Redis 7  │
   │  public    │◀────────────────────────┴────────────│  (pub/sub, │
   │  (no auth) │                                     │  locks)    │
   └────────────┘                                     └─────┬──────┘
                                                      subscribe
        HTTP-проверки сайтов                          ┌─────┴──────┐
   ┌────────────┐        ────────── httpx ──────────▶ │ scheduler  │
   │ demo-sites │◀─────────────────────────────────── │ (asyncio)  │
   │ (emulator) │        POST /mode/{name} (UI)       └────────────┘
   └────────────┘
```

Процессы (docker compose services):

| Сервис      | Назначение                                   | Порт (host)      |
|-------------|----------------------------------------------|------------------|
| `frontend`  | nginx отдаёт SPA и проксирует `/api` → api    | 8080             |
| `api`       | FastAPI (uvicorn), REST + SSE, миграции, сид | 8000             |
| `scheduler` | тот же образ, точка входа `python -m app.scheduler` | —          |
| `db`        | PostgreSQL 16                                 | 127.0.0.1:5432   |
| `redis`     | Redis 7                                       | внутренний       |
| `demo-sites`| эмулятор проверяемых сайтов                   | 8090             |
| `db-test`   | PostgreSQL для pytest (профиль `test`)        | —                |

## 2. Схема БД (PostgreSQL, всё UTC/timestamptz)

```sql
users(
  id uuid pk default gen_random_uuid(),
  email text not null unique,              -- хранится в lower()
  password_hash text not null,             -- argon2
  created_at timestamptz not null default now()
)

groups(                                     -- «группа проверок»
  id uuid pk default gen_random_uuid(),
  owner_id uuid not null references users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 100),
  description text not null default '',
  public_slug text unique,                  -- null = группы нет на публичной странице
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)

alert_emails(                               -- адреса оповещений, свои на группу
  id uuid pk default gen_random_uuid(),
  group_id uuid not null references groups(id) on delete cascade,
  email text not null,
  created_at timestamptz not null default now(),
  unique (group_id, email)
)

checks(
  id uuid pk default gen_random_uuid(),
  group_id uuid not null references groups(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 100),
  url text not null,                        -- http/https, валидируется
  interval_seconds int not null check (interval_seconds between 30 and 3600),
  timeout_seconds int not null check (timeout_seconds between 1 and 30),
  expected_status int not null default 200,
  expected_body text,                       -- null = не проверять подстроку
  failure_threshold int not null default 3 check (failure_threshold between 1 and 10),
  paused bool not null default false,
  show_on_public bool not null default false,
  -- домен, обновляется шедулером:
  state text not null default 'unknown' check (state in ('unknown','up','down')),
  consecutive_failures int not null default 0,
  failing_since timestamptz,                -- первая неудача текущей серии
  last_checked_at timestamptz,
  next_run_at timestamptz,                  -- расписание, переживает рестарт
  in_flight_until timestamptz,              -- claim от параллельного самозапуска
  -- денормализованный последний результат:
  last_ok bool,
  last_status_code int,
  last_response_time_ms int,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)
-- индексы:
--   ix_checks_due      on checks(next_run_at) where not paused
--   ix_checks_group    on checks(group_id)

check_results(
  id bigint generated always as identity pk,
  check_id uuid not null references checks(id) on delete cascade,
  checked_at timestamptz not null default now(),
  ok bool not null,
  status_code int,
  response_time_ms int,                     -- замер всегда, даже при ошибке сети
  error text
)
-- индекс ix_results_check_time on check_results(check_id, checked_at desc)

incidents(
  id uuid pk default gen_random_uuid(),
  check_id uuid not null references checks(id) on delete cascade,
  started_at timestamptz not null,          -- = failing_since серии
  ended_at timestamptz,                     -- null = открыт
  notified_down_at timestamptz,             -- когда ушло (или отмечено suppressed) down-письмо
  notified_up_at timestamptz,
  last_error text
)
--   ix_incidents_check on incidents(check_id, started_at desc)
--   ix_incidents_open  on incidents(check_id) where ended_at is null

maintenance_windows(
  id uuid pk default gen_random_uuid(),
  owner_id uuid not null references users(id) on delete cascade,
  check_id uuid references checks(id) on delete cascade,   -- ровно одна
  group_id uuid references groups(id) on delete cascade,   -- из двух целей
  starts_at timestamptz not null,
  ends_at timestamptz not null check (ends_at > starts_at),
  note text not null default '',
  created_at timestamptz not null default now(),
  check (num_nonnulls(check_id, group_id) = 1)
)
--   ix_maintenance_active on maintenance_windows(starts_at, ends_at)

email_outbox(                               -- эмуляция почты (и журнал suppressed)
  id uuid pk default gen_random_uuid(),
  owner_id uuid not null references users(id) on delete cascade,
  group_id uuid references groups(id) on delete cascade,
  check_id uuid references checks(id) on delete cascade,
  to_email text not null,
  subject text not null,
  body text not null,
  kind text not null check (kind in ('down','up','test')),
  status text not null check (status in ('sent','suppressed')),
  suppress_reason text,                     -- например 'maintenance_window'
  created_at timestamptz not null default now()
)
```

## 3. Доменные правила (ядро корректности)

### 3.1 Выполнение проверки

`perform_http_check`: GET `url`, `timeout = timeout_seconds` (httpx connect+
read+write+pool), follow_redirects=true. Успех = `status_code == expected_status`
И (`expected_body is null` ИЛИ подстрока в теле). Всё остальное (таймаут,
ошибка сети, не тот код, нет подстроки) = неудача; `error` — человекочитаемая
строка. `response_time_ms` — целое, замеряется всегда.

### 3.2 Claim: проверка не запускается параллельно сама с собой

Перед выполнением (и шедулером, и ручным «запустить сейчас»):

```sql
UPDATE checks SET in_flight_until = now() + (timeout_seconds + 10) * interval '1 sec'
WHERE id = :id AND paused = false
  AND (in_flight_until IS NULL OR in_flight_until <= now())
RETURNING id;
```

0 строк → кто-то уже выполняет, пропускаем. После завершения
`in_flight_until = NULL`. Протухший claim самолечится по времени.

### 3.3 Обработка результата (одна транзакция)

1. insert `check_results`;
2. обновить `last_*`, `last_checked_at`;
3. неудача: `consecutive_failures += 1`; если стала 1 — `failing_since = now`.
   Успех: `consecutive_failures = 0`, `failing_since = NULL`;
4. состояние: `state='down'` когда `consecutive_failures >= failure_threshold`;
   `state='up'` на успехе; до порога при неудачах остаётся прежним (`up`);
5. инциденты:
   - нет открытого И порог достигнут → создать incident
     (`started_at = failing_since`, `last_error`), событие `incident.opened`;
     если НЕ в окне обслуживания → down-письмо (один раз, `notified_down_at`),
     иначе записать suppressed-строку в outbox (без `notified_down_at`);
   - открытый И `notified_down_at IS NULL` И сейчас НЕ в окне → отправить
     down-письмо (этот путь закрывает «окно кончилось, сайт всё ещё лежит»);
   - открытый И успех → `ended_at = now`, событие `incident.closed`;
     если НЕ в окне → up-письмо (`notified_up_at`), иначе suppressed-строка;
6. событие `check.update` (см. §5).

### 3.4 Окно обслуживания

Действует, если существует окно с `(check_id = :check OR group_id = :group)
AND starts_at <= now() < ends_at`. В окно: проверки идут, результаты и
инциденты пишутся, письма подавляются (suppressed-строки видны в Mailbox).
Проход шедулера `window_end_notification_pass` (каждые ~5с): открытые
инциденты с `notified_down_at IS NULL` и уже НЕ в окне → отправить down.

### 3.5 Шедулер

Одноинтервальный asyncio-цикл (тик 1с): выбрать due-проверки
(`not paused AND next_run_at <= now`), для каждой — claim; при успехе сразу
`next_run_at = now + interval_seconds` и запустить задачу. Пропущенные по
перегрузке/простою слоты не навёрстываются. Пауза: не выбирается; резюм:
`next_run_at = now`. Рестарт: расписание читается из БД, простои не создают
результатов (дыры в истории), инциденты не создаются. Leader-lock Redis
`scheduler:leader` (SET NX PX, пролонгация), второй экземпляр завершается.
Ежесуточно: удаление `check_results` старше `RESULTS_RETENTION_DAYS` (90).

### 3.6 Статус группы (вычисляемый)

По непоставленным на паузу проверкам группы: есть down →
`major_outage` если down все, иначе `partial_outage`; нет down, но есть
`unknown` → `degraded`; иначе `operational`. Все на паузе → `maintenance`?

Нет: `paused` не влияет — только up/down/unknown. Группа без активных
проверок → `operational`.

### 3.7 История (агрегация на лету)

`GET /api/checks/{id}/history?period=day|week|month`:
бакеты `date_bin`: day → 5 мин, week → 1 час, month → 6 часов. На бакет:
`count`, `ok_count`, `uptime_ratio = ok_count/count` (null если 0),
`avg_response_ms`, `max_response_ms`. Плюс `summary` за весь период и список
инцидентов, пересекающихся с периодом. Дыры (нет данных) — бакеты с
`count = 0`, `uptime_ratio = null`.

### 3.8 Письма

Одно `down` на инцидент, одно `up` на закрытие. Адреса — `alert_emails`
группы; если у группы адресов нет — письмо пишется в outbox на
`noreply@pulse.local` с пометкой в теле (доказуемо в UI). Тема:
`[Pulse] DOWN: {check.name}` / `[Pulse] UP: {check.name}`. Транспорт: если
задан `SMTP_HOST` — aiosmtplib, иначе статус `sent` в outbox (эмуляция).

## 4. REST API

Авторизация: `Authorization: Bearer <jwt>`; JWT HS256, `sub=user_id`,
`exp = 24h`. Ошибки: `{"detail": "..."}` + правильные коды (401/403/404/409/422).
Все ресурсы скоуплены по владельцу (owner) — чужое = 404.

Базовый префикс `/api`. Формат дат — ISO 8601 UTC.

### Auth
```
POST /api/auth/register {email, password(>=8)}        → 201 {token, user:{id,email}}
POST /api/auth/login    {email, password}             → 200 {token, user:{id,email}}
GET  /api/me                                           → 200 user
```

### Overview (дашборд)
```
GET /api/overview → 200 {
  groups: [{
    id, name, description, public_slug, status,            // §3.6
    alert_emails: [{id, email}],
    checks: [CheckView]                                    // §CheckView, по created_at
  }]
}
```

**CheckView** (используется везде, где есть проверка):
```
{ id, group_id, name, url, interval_seconds, timeout_seconds, expected_status,
  expected_body, failure_threshold, paused, show_on_public, state,
  consecutive_failures, last_checked_at, last_ok, last_status_code,
  last_response_time_ms, last_error,
  open_incident: {id, started_at} | null,                 // текущее падение
  uptime_24h: number|null }                                // ok/total за 24ч
```

### Groups
```
POST   /api/groups {name, description?}                        → 201 GroupView
GET    /api/groups                                            → [GroupView без checks]
PATCH  /api/groups/{id} {name?, description?, public_slug?}    → GroupView
        public_slug: null — убрать с публички; "" — нельзя; строка — задать
        (валидация: 3-64, [a-z0-9-], уникальность → 409)
DELETE /api/groups/{id}                                       → 204
POST   /api/groups/{id}/emails {email}                        → 201 {id, email}
DELETE /api/groups/{id}/emails/{email_id}                     → 204
POST   /api/groups/{id}/public-slug/generate                  → 200 {public_slug}
```

### Checks
```
POST   /api/checks {group_id, name, url, interval_seconds, timeout_seconds,
                    expected_status?, expected_body?, failure_threshold?,
                    show_on_public?}                           → 201 CheckView
GET    /api/checks?group_id=&paused=                          → [CheckView]
GET    /api/checks/{id}                                       → 200 CheckDetail
PATCH  /api/checks/{id}  {любые поля, вкл. paused}            → 200 CheckView
DELETE /api/checks/{id}                                       → 204
POST   /api/checks/{id}/run                                   → 200 CheckView  // ручной запуск сейчас
GET    /api/checks/{id}/history?period=                       → §3.7
GET    /api/checks/{id}/results?limit<=200&before=<iso>       → {items:[CheckResult], next_before|null}
POST   /api/checks/{id}/pause | /resume                       → 200 CheckView  // sugar для PATCH paused
```
`CheckResult`: `{id, checked_at, ok, status_code, response_time_ms, error}`.
При создании/резюме: `next_run_at = now`, `state` не сбрасывается.
Смена `interval/timeout` применяется со следующего запуска.

`CheckDetail` = CheckView + `incidents: [{id, started_at, ended_at, duration_s|null, last_error}]` (последние 50) + `group: {id, name}`.

### Maintenance
```
GET    /api/maintenance-windows?active=true|false            → [{id, check_id, group_id,
                                                               starts_at, ends_at, note,
                                                               check_name|group_name}]
POST   /api/maintenance-windows {check_id | group_id, starts_at, ends_at, note?} → 201
PATCH  /api/maintenance-windows/{id} {starts_at?, ends_at?, note?}               → 200
DELETE /api/maintenance-windows/{id}                                            → 204
```

### Mailbox (эмуляция почты)
```
GET /api/mailbox?limit=100                     → {items: [{id, group_id, check_id, to_email,
                                                 subject, body, kind, status, suppress_reason,
                                                 created_at}]}   // новые сверху
POST /api/groups/{id}/emails/{email_id}/test   → 201 outbox-строка kind=test
```

### Публичное (без авторизации)
```
GET /api/public/{slug} → 200 {
  group: {name, description},
  status,                                    // §3.6 по public-проверкам
  checks: [{id, name, state, last_checked_at, uptime_24h}]   // только show_on_public=true
} | 404
GET /api/public/{slug}/events                 → SSE, только события этой группы и только public-проверок
```

### Служебные
```
GET /api/health → {"status":"ok", "scheduler_heartbeat": <iso|null>}
```
`scheduler_heartbeat` — ключ в Redis `scheduler:heartbeat` (TTL 10с), пишется каждым тиком.

## 5. SSE

`GET /api/events?token=<jwt>` (EventSource заголовки не умеет — token в query).
Ответ `text/event-stream`; `retry: 3000`; heartbeat `: ping` каждые 15с.

События (имя события = поле `type`):

```
event: check.update
data: {"type":"check.update","check_id":"…","group_id":"…","owner_id":"…",
       "state":"up|down|unknown","ok":true,"status_code":200,
       "response_time_ms":123,"checked_at":"…","paused":false,
       "consecutive_failures":0,"failure_threshold":3,
       "show_on_public":true,"public_slug":"demo-status|null"}

event: incident.opened
data: {"type":"incident.opened","incident_id":"…","check_id":"…","group_id":"…",
       "owner_id":"…","started_at":"…","last_error":"…","show_on_public":…,"public_slug":…}

event: incident.closed
data: {"type":"incident.closed","incident_id":"…","check_id":"…","group_id":"…",
       "owner_id":"…","started_at":"…","ended_at":"…","show_on_public":…,"public_slug":…}
```

Семантика для клиента: любое событие → invalidate `['overview']`,
`['check', check_id]`, `['history', check_id]`, `['mailbox']`; для публичного
потока — invalidate `['public', slug]`. Сервер фильтрует: `/api/events` —
только события владельца токена; `/api/public/{slug}/events` — только
`show_on_public=true` и `public_slug == slug`.

## 6. Эмулятор demo-sites

```
GET  /ok                       → 200 "OK"
GET  /slow/{ms}                → спит ms, 200 "OK"
GET  /error                    → 500 "Internal Server Error"
GET  /hang                     → не отвечает никогда
GET  /flaky/{n}                → каждый n-й запрос 500
GET  /site/{name}              → ответ по текущему режиму name
POST /mode/{name} {mode}       → установить режим: "ok"|"error"|"dead"|"slow"|"flaky"
                               + optional {"delay_ms": 5000} для slow
GET  /modes                    → {name: mode} — все текущие режимы
GET  /healthz
```
Режимы: `ok` → 200 "OK from {name}"; `error` → 500; `dead` → висит (не
отвечает до таймаута клиента); `slow` → спит `delay_ms` (default 10000) → 200;
`flaky` → каждый 2-й запрос 500. Состояние в памяти процесса. CORS: allow all
(демо-сервис). Проверяемые URL из сида: `http://demo-sites:8090/site/<name>`.

## 7. Env

```
DATABASE_URL=postgresql+asyncpg://pulse:pulse@db:5432/pulse
REDIS_URL=redis://redis:6379/0
JWT_SECRET=change-me                    # обязателен в prod
SEED_DEMO=1                             # сид demo-данных при старте api (идемпотентно)
CORS_ORIGINS=http://localhost:8080
SMTP_HOST= SMTP_PORT=25 SMTP_USER= SMTP_PASSWORD= MAIL_FROM=pulse@localhost   # пусто = эмуляция
RESULTS_RETENTION_DAYS=90
SCHEDULER_TICK_SECONDS=1.0
LOG_LEVEL=INFO
```

## 8. Seed (SEED_DEMO=1, идемпотентно)

- user `demo@pulse.dev` / `demo1234`;
- группа `Production` (slug `demo-status`, email `demo@pulse.dev`):
  - «Main site» → site/main, 60с, таймаут 10с, порог 3, public;
  - «Slow API» → site/slow, 60с, таймаут 5с, порог 2, public (режим slow c delay 3000 — отвечает, но медленно);
  - «Flaky endpoint» → site/flaky, 30с, таймаут 10с, порог 3;
- группа `Internal` (без публичности, email нет):
  - «Legacy service» → site/dead, 60с, таймаут 10с, порог 3;
- окно обслуживания: группа Internal, завтра 02:00–04:00 UTC, note «DB upgrade»;
- начальные режимы эмулятора: main=ok, slow=slow(3000), flaky=ok, dead=ok.

## 9. Design direction (frontend)

Продукт — ops-инструмент: спокойный, плотный, информационный. Тёмная тема
по умолчанию (переключатель не обязателен). Шрифт — системный стек
`system-ui, -apple-system, "Segoe UI", sans-serif`. Дизайн-токены (hex, не
имена Tailwind — использовать ровно эти значения):

| Роль | Значение |
|---|---|
| Фон страницы | `#020617` |
| Поверхность карточки/графика | `#0f172a` |
| Хайрлайн-рамка | `rgba(255,255,255,0.08)` |
| Ink primary / secondary / muted | `#f1f5f9` / `#94a3b8` / `#64748b` |
| Gridline (1px solid, recessive) | `#1e293b` |
| Ось (линия) | `#334155` |
| Статус `up` (good) | `#0ca30c` |
| Статус `down` (critical) | `#d03b3b` |
| Статус `paused` (warning) | `#fab219` |
| Статус `unknown` | `#64748b` |
| Обслуживание / info-акцент | `#3987e5` |
| Единственная серия линии графика | `#3987e5` (2px, round join/cap) |
| Availability-бар: ratio=1 | `#0ca30c` |
| Availability-бар: 0<ratio<1 | `#ec835a` |
| Availability-бар: ratio=0 | `#d03b3b` |
| Availability-бар: дыра (null) | пусто (цвет поверхности) |

Правила: статусный цвет никогда не несёт смысл один — всегда рядом
иконка/текст (точка ● + подпись). Текст не красится в цвет серии — только
ink-токены. Одна серия — без легенды (заголовок называет её). Двух осей
нет: график времени ответа и полоса доступности — два отдельных графика
друг под другом. Тултип обязателен: на линии — crosshair+value, на барах —
per-bar. Числа в таблицах и тиках осей — `font-variant-numeric:
tabular-nums`. Бары ≤24px толщиной, 2px поверхности-зазор между соседними,
дата-конец 4px скруглён, у базы — квадрат. Маркеры ≥8px с 2px кольцом
цвета поверхности. Gridline — solid hairline, не dashed.

Ключевые экраны: сайдбар-навигация слева (Dashboard, Maintenance, Mailbox,
Demo, — и выход); таблица проверок с живыми статусами (точка, имя, URL,
время ответа, последняя проверка «N мин назад», длительность текущего
падения, интервал); карточка проверки с графиком ответа (линия) и %
доступности (число + полоса-бар по бакетам); журнал инцидентов таблицей;
Mailbox — список писем с бейджами sent/suppressed; публичная страница —
крупный общий статус-баннер + строки проверок, без навигации приватной
части. Пустые состояния с подсказкой и CTA. Кнопка «Run now» — с локальным
состоянием загрузки. Все времена — локальная зона браузера, ISO-парсинг.

Графики (Recharts): линия времени ответа (мс) по бакетам, дыры = разрывы
линии (`connectNulls={false}`); доступность — полоса бакетов на 100%-шкале.
Оси: время (локальное), мс; тултипы с конкретными значениями.
