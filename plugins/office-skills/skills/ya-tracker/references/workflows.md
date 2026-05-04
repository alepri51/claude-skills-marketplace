# Workflows API

Управление workflow (бизнес-процесс очереди: статусы + переходы + типы задач) через
Tracker API. Точные схемы тела для `POST`/`PATCH` в публичной api-ref Яндекса
не задокументированы — действуй по принципу: сначала прочитать существующий
workflow, скопировать его shape, изменить нужные поля, отправить обратно.

## Endpoints (под капотом)

| Tool | HTTP | Path |
|------|------|------|
| `workflows_get_all` | GET | `/v2/workflows` |
| `workflow_get` | GET | `/v2/workflows/{id}` |
| `workflow_create` | POST | `/v2/workflows` |
| `workflow_update` | PATCH | `/v2/workflows/{id}` |
| `workflow_delete` ⚠ | DELETE | `/v2/workflows/{id}` |
| `workflow_get_steps` | GET | `/v2/workflows/{id}/steps` (experimental) |
| `workflow_get_transitions` | GET | `/v2/workflows/{id}/transitions` (experimental) |

`{id}` — идентификатор вида `W163`.

## Получить shape существующего workflow

```
python .claude/skills/ya-tracker/scripts/tracker.py \
  workflow_get '{"workflow_id":"W163"}'
```

Ответ возвращается as-is (без формaтера) — там лежат поля `steps`,
`transitions`, `statuses`, `issueType`, `queue` и т.п. Используй именно
этот JSON как референс для последующих `workflow_update` / `workflow_create`.

Если нужно посмотреть только переходы или шаги — `workflow_get_steps` /
`workflow_get_transitions`. Если они вернут `404`, читай поля `steps`
и `transitions` прямо из ответа `workflow_get`.

## Обновить (PATCH)

Передаются только изменяемые поля — остальное Tracker не трогает.

```
python .claude/skills/ya-tracker/scripts/tracker.py \
  workflow_update '{"workflow_id":"W163","body":{"name":"Релизный процесс"}}'
```

Если API ответит `405`/`400` на PATCH — ту же операцию провести как
`workflow_update` через PUT не получится (в скилле метод PATCH);
можно временно изменить `_dispatch` или сделать запрос напрямую через
`curl` для разовых случаев.

## Создать (POST)

Самый надёжный путь:

1. `workflow_get` → возьми существующий workflow близкого типа.
2. Скопируй JSON, поменяй `name`, `key`, `id`, привязки к очереди/типу
   задач.
3. Отправь как `body` в `workflow_create`.

```
python .claude/skills/ya-tracker/scripts/tracker.py \
  workflow_create '{"body": { ... raw JSON ... }}'
```

## Удалить (DESTRUCTIVE)

```
python .claude/skills/ya-tracker/scripts/tracker.py \
  workflow_delete '{"workflow_id":"WTEST","confirm":true}'
```

Без `"confirm": true` команда вернёт `Error 400` без обращения к API.
Удаление workflow, привязанного к используемой очереди, скорее всего
вернёт ошибку API — отвязать сначала через UI или `queue_*` ops.

## Связанные сущности

- Список статусов в системе (id/key) — `get_statuses`
- Список резолюций — `get_resolutions`
- Список типов задач — `get_issue_types`
- Транзиции конкретной задачи (не workflow) — `issue_get_transitions`
  + `issue_execute_transition`

## Документация Яндекса

- Концепция: `https://yandex.ru/support/tracker/ru/manager/workflow`
- API-справочник (общий): `https://yandex.ru/support/tracker/ru/api-ref/about-api`

Публичной страницы api-ref именно для `/v2/workflows` нет — endpoint
живой, но не индексируется поиском. Если нужен exact request schema —
снять его с реального ответа `workflow_get` или связаться с поддержкой
Tracker.
