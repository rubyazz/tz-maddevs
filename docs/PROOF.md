# Доказательства работоспособности (PROOF)

Все сценарии выполнены 2026-10-05/06 на живом стеке
`docker compose up -d --build` (macOS, Docker 28.1.1). Выводы — реальные
ответы API/БД, сокращённо. Повторить любой сценарий можно по шагам ниже
(токен берётся логином демо-пользователя).

## 0. Стек жив

```
$ curl -s localhost:8000/api/health
{"status":"ok","scheduler_heartbeat":"2026-10-05T23:58:16.701571+00:00"}
$ docker compose ps
api Up (healthy) · db Up (healthy) · redis Up (healthy) · scheduler Up · frontend Up · demo-sites Up
```

heartbeat пишется каждым тиком шедулера (TTL 10с) — живой proof пульса.

## 1. Порог падения: кратковременный сбой — не падение

Режим `main` → `error`, три ручных прогона (порог «Main site» = 3):

```
run 1: {"state":"up","consecutive_failures":1,...}   ← ещё не падение
run 2: {"state":"up","consecutive_failures":2,...}
run 3: {"state":"down","consecutive_failures":3,"open_incident":{"started_at":"…23:08:04"}}
mailbox: down  sent  [Pulse] DOWN: Main site
```

## 2. Ровно одно письмо DOWN, тишина между, одно UP

Ещё 3 неудачных прогона → писем по-прежнему 1. Возврат в `ok` + прогон:

```
mailbox:
  up    sent  [Pulse] UP: Main site
  down  sent  [Pulse] DOWN: Main site
incident: {"started_at":"23:08:04","ended_at":"23:08:16","duration_s":12}
```

## 3. Окно обслуживания: письма подавляются, после конца — уходят

Окно на группу Production (5 минут), `main` → `error`, 3 прогона:

```
mailbox (внутри окна):
  down  suppressed  maintenance_window  [Pulse] DOWN: Main site   ← и только
```

Окно закрыто раньше времени (PATCH `ends_at=now-1s`), ждём ≤5с:

```
mailbox (после конца окна):
  down  sent       [Pulse] DOWN: Main site     ← отложенное письмо ушло
  down  suppressed maintenance_window  …
  up    sent      …
```

Инцидент при этом открыт с самого порога — проверки в окне шли, статусы
писались.

## 4. Параллельный самозапуск невозможен

`main` → slow 9000ms; первый ручной прогон в фоне, второй сразу:

```
second (immediately): 409 {"detail":"Check is already running"}
first: 200 in 9.347767s {"state":"up","last_response_time_ms":9113}
```

Механика — атомарный claim `in_flight_until` (работает и между
процессами); протухший claim самолечится по TTL.

## 5. 50 проверок × 30с не мешают друг другу

Группа «Load test»: 49 проверок на `/ok` + 1 на `/hang` (таймаут 30с),
все с интервалом 30с. Через 75с:

```
checks_with_results=50  total=100  avg=2.0  min=2  max=2
```

Каждая проверка дала ровно 2 результата (30с интервал), ни одна не
потерялась и не задвоилась; висящий `/hang` никого не задержал (иначе
были бы пропуски). UI: overview 0.28с, публичная страница 0.017с.
Логи шедулера без ошибок.

## 6. Месяц истории открывается быстро

`make seed-history` → 4 проверки × ~85K синтетических результатов:

```
day:   0.305s  buckets=289  uptime=0.9651  p95=410ms
week:  0.047s  buckets=169  uptime=0.9813  p95=415ms
month: 0.171s  buckets=121  uptime=0.9839  p95=413ms
```

## 7. Рестарт: расписание и настройки живут, простой — дыра

`docker compose restart api scheduler`, пауза ~70с:

```
results before: 887 → after: 893
Flaky endpoint: 2 результата за 70с (30с интервал)
остальные (60с): по 1
incidents: 6 (не выросли — простой не создал падений)
```

Проверки продолжились с прежними интервалами; пропущенное время —
бакеты без данных (дыры на графике), не падение.

## 8. Realtime: две вкладки + публичный поток

Три параллельных SSE-подписчика на 35с (2 приватных + 1 публичный), в
середине — ручной прогон:

```
client1: 5 events; client2: 5 events          ← обе вкладки в фокусе
public:  3 events, только check_id публичных (Main site ×2, Slow API ×1)
         Flaky/Legacy (не публичные) в поток не попали
```

## 9. Публичная страница показывает только разрешённое

```
GET /api/public/demo-status
{"group":{"name":"Production",...},"status":"operational",
 "checks":[{"name":"Main site","state":"up"},{"name":"Slow API","state":"up"}]}
```

«Flaky endpoint» (show_on_public=false) и вся группа Internal на странице
нет. Неизвестный slug → 404.

## 10. UI проверен браузером (headless Chromium + DOM-аудит)

Логин демо-аккаунтом → dashboard → карточка проверки → публичная страница:

```
фон страницы rgb(2,6,23) (=#020617, токен контракта)
навигация: Dashboard/Maintenance/Mailbox/Demo — есть
таблица: 2 группы, 4 проверки, статус-точки #0ca30c (up)
check detail: SVG-график времени ответа + 289 бакетов доступности,
  плитки: uptime 96.47%, avg 419ms, p95 411ms, инцидентов 3
public: баннер "All systems operational", 2 проверки, без приватного сайдбара
ошибок JS в консоли: 0
```

(Попутно найден и починен краш React #31 на /demo — объект режима
рендерился как React-child; зафиксировано в истории коммитов.)

## 11. Тесты и линтер

```
$ make test        # в контейнерах, против отдельной test-БД
41 passed (29 unit + 12 integration) 
$ cd backend && uv run ruff check app tests scripts
All checks passed!
```

Покрытие юнит: машина состояний инцидентов (15 кейсов), валидация схем,
письма. Интеграция (реальная PostgreSQL): эксклюзивность claim,
резедуling, полный цикл инцидент→письма, подавление окном и отложенная
отправка, бакеты истории, API: auth/CRUD/IDOR/публичная фильтрация.
