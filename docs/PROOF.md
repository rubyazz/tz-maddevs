# Доказательства (PROOF)

Живой стек `docker compose up`, macOS/Docker 28. Выводы — реальные ответы
API/БД (сокращённо). Токен: логин `demo@pulse.dev`.

## 0. Стек жив

```
$ curl -s localhost:8000/api/health
{"status":"ok","scheduler_heartbeat":"2026-10-05T23:58:16.701571+00:00"}
```
heartbeat пишется каждым тиком шедулера (TTL 10с).

## 1. Кратковременный сбой — не падение

`main` → error, три ручных прогона (порог 3):

```
run1 {"state":"up","consecutive_failures":1}  run2 …2
run3 {"state":"down","consecutive_failures":3,"open_incident":{…}}
mailbox: down sent [Pulse] DOWN: Main site
```

## 2. Одно письмо DOWN, тишина, одно UP

+3 неудачных прогона → писем по-прежнему 1. `main` → ok, прогон:

```
mailbox: up sent [Pulse] UP: Main site · down sent [Pulse] DOWN: Main site
incident {"duration_s":12}
```

## 3. Окно обслуживания

Окно на группу Production, `main` → error, 3 прогона:

```
внутри окна:  down suppressed maintenance_window [Pulse] DOWN: Main site
окно закрыто (PATCH ends_at=now), ≤5с:
              down sent [Pulse] DOWN: Main site   ← отложенное ушло
```

## 4. Самопараллельность исключена

`main` → slow 9000ms; первый прогон в фоне, второй сразу:

```
second: 409 {"detail":"Check is already running"}
first:  200 in 9.35s {"state":"up","last_response_time_ms":9113}
```

## 5. 50 проверок × 30с

49 на `/ok` + 1 на `/hang` (timeout 30), 75с:

```
checks_with_results=50 total=100 avg=2.0 min=2 max=2
overview 0.28s · public 0.017s · логи шедулера чисты
```

## 6. Месяц истории — быстро

`make seed-history` (4 × ~85K строк):

```
day 0.305s (289 buckets) · week 0.047s · month 0.171s (121 buckets)
```

## 7. Рестарт

`docker compose restart api scheduler`, 70с:

```
results 887 → 893; Flaky(30с)=2, остальные(60с)=1; incidents не выросли
```
Простой — дыра в истории, не падение.

## 8. Realtime: две вкладки + публичный поток

3 SSE-подписчика на 35с, в середине ручной прогон:

```
client1: 5 events; client2: 5 events
public: 3 events — только публичные проверки (Flaky/Legacy нет)
```

## 9. Публичная страница — только разрешённое

```
GET /api/public/demo-status → Main site, Slow API (show_on_public),
"Flaky endpoint" и группа Internal отсутствуют; неизвестный slug → 404
```

## 10. UI (headless Chromium, DOM-аудит)

```
фон rgb(2,6,23)=#020617 · навигация · 2 группы · 4 проверки · точки #0ca30c
check detail: SVG-график + 289 бакетов · плитки 96.47% / 419ms / p95 411ms
public: баннер "All systems operational" · без приватного сайдбара
ошибок JS: 0   (попутно пойман и починен React #31 на /demo)
```

## 11. Тесты и линтер

```
$ make test                 $ uv run ruff check app tests scripts
41 passed                   All checks passed!
```

Юнит: машина инцидентов, схемы, письма. Интеграция (реальная PG): claim,
полный цикл, подавление окном, бакеты; API: auth/CRUD/IDOR/публичность.
