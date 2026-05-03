---
name: ya-tracker
description: >
  CLI для Яндекс Трекера: чтение и запись задач, комментарии, вложения,
  связи, переходы статусов, очереди, пользователи, метаданные. Используй
  этот скилл всегда, когда нужно что-то сделать в Трекере: взять задачу
  в работу, собрать контекст по задаче (описание + комментарии + вложения
  + связи), создать подзадачу, прикрепить артефакт, оставить комментарий,
  закрыть задачу. Триггер-фразы: «возьми задачу DE-1569», «покажи открытые
  в очереди BACK», «собери контекст задачи», «создай подзадачу в DE»,
  «прикрепи PLAN.md к DE-1600», «скачай вложение из задачи», «оставь
  комментарий в родителе», «закрой подзадачу с резолюцией fixed»,
  «найди задачи пользователя за неделю». Все 40+ операций Tracker API v2
  доступны через один CLI. Токен из корневого .env.
compatibility: >
  Требуется Python 3.10+ и пакеты: aiohttp, mcp. Установка:
    python -m pip install aiohttp mcp
  Креденшлы: TRACKER_TOKEN + (TRACKER_CLOUD_ORG_ID или TRACKER_ORG_ID)
  в корневом .env. Проверка: python scripts/tracker.py get_myself '{}'
---

# ya-tracker

CLI для Yandex Tracker API v2. Сорок+ инструментов одной командой.

## Когда этот скилл полезен

Типичные запросы:

- «Возьми задачу DE-1569» → читать описание, комментарии, связи,
  скачать вложения (см. `references/gather-task-context.md`)
- «Покажи открытые задачи в очереди BACK» →
  `issues_find 'Queue: BACK AND Status: open'`
- «Создай подзадачу в DE с тегом bnmap-api-v2» →
  `issue_create` (см. `references/create-subtasks.md`)
- «Прикрепи PLAN.md к DE-1600» → `issue_upload_attachment`
- «Скачай TRD.pdf из DE-1569» → `issue_download_attachment`
- «Скачай ВСЕ вложения DE-1569» → `issue_download_all_attachments`
- «Свяжи DE-1601 с DE-1600 через depends on» → `issue_create_link`
- «Закрой DE-1600 с резолюцией fixed» → `issue_close`

## Как вызывать — через CLI

Общий формат:

```
python .claude/skills/ya-tracker/scripts/tracker.py <tool> '<json_args>'
```

Список всех инструментов:

```
python .claude/skills/ya-tracker/scripts/tracker.py list-tools
```

Примеры:

```
# получить задачу
python .claude/skills/ya-tracker/scripts/tracker.py \
  issue_get '{"issue_key":"DE-1569"}'

# найти задачи (страница 1, по 20 на страницу)
python .claude/skills/ya-tracker/scripts/tracker.py \
  issues_find '{"query":"Queue: BACK AND Status: open","per_page":20}'

# добавить комментарий (одна строка)
python .claude/skills/ya-tracker/scripts/tracker.py \
  issue_add_comment '{"issue_key":"DE-1569","text":"Текст комментария"}'

# добавить multi-line комментарий из файла (UTF-8) — без PowerShell cp1251 / JSON-escape boilerplate
python .claude/skills/ya-tracker/scripts/tracker.py \
  issue_add_comment '{"issue_key":"DE-1569","text_file":".planning/tracker/DE-1569/comment.md"}'

# создать подзадачу
python .claude/skills/ya-tracker/scripts/tracker.py \
  issue_create '{"queue":"DE","summary":"Краткое название","parent":"DE-1569","tags":["tag1","tag2"]}'

# закрыть задачу
python .claude/skills/ya-tracker/scripts/tracker.py \
  issue_close '{"issue_key":"DE-1569","resolution_id":"fixed","comment":"Готово"}'

# скачать все вложения задачи параллельно (filename auto-resolves)
# save_dir — канонический ключ; save_path принимается как alias.
# Коллизия имён: auto-suffix _2, _3 … (для force указать "overwrite": true).
python .claude/skills/ya-tracker/scripts/tracker.py \
  issue_download_all_attachments '{"issue_key":"DE-1569","save_dir":"downloads/DE-1569"}'

# скачать одно вложение в конкретный путь (overwrite файла, если он уже есть)
python .claude/skills/ya-tracker/scripts/tracker.py \
  issue_download_attachment '{"issue_key":"DE-1569","attachment_id":12345,"save_dir":".tmp/refresh","overwrite":true}'

# метаданные очереди (queue_id, не queue!)
python .claude/skills/ya-tracker/scripts/tracker.py \
  queue_get_metadata '{"queue_id":"DE"}'

# удалить вложение из задачи
python .claude/skills/ya-tracker/scripts/tracker.py \
  issue_delete_attachment '{"issue_key":"DE-1569","attachment_id":12345}'

# удалить очередь (РАЗРУШИТЕЛЬНО — обязателен confirm:true)
python .claude/skills/ya-tracker/scripts/tracker.py \
  queue_delete '{"queue_id":"SANDBOX","confirm":true}'
```

## Полный набор инструментов

**Issues — чтение:**
- `issue_get`, `issues_find`, `issues_count`
- `issue_get_comments`, `issue_get_links`, `issue_get_transitions`
- `issue_get_attachments`, `issue_download_attachment`, `issue_download_all_attachments`
- `issue_get_checklist`, `issue_get_worklogs`

**Issues — запись:**
- `issue_create`, `issue_update`
- `issue_execute_transition`, `issue_close`
- `issue_add_comment`, `issue_update_comment`, `issue_delete_comment`
- `issue_upload_attachment`, `issue_delete_attachment`
- `issue_delete_checklist_item`, `issue_delete_checklist`
- `issue_get_url`

**Worklogs:** `issue_add_worklog`, `issue_update_worklog`, `issue_delete_worklog`

**Links:** `issue_create_link`, `issue_delete_link`

**Queues:** `queues_get_all`, `queue_get_metadata`, `queue_get_fields`,
`queue_get_tags`, `queue_get_versions`, `queue_delete_macro` ⚠, `queue_delete` ⚠

**Projects:** `project_delete` ⚠

**Boards:** `board_delete` ⚠, `board_delete_column` ⚠

⚠ — разрушительные операции. Требуют параметр `"confirm": true` в JSON
аргументах, иначе вернётся `Error 400` без обращения к API. Tracker API
не поддерживает удаление самой задачи (`issue`), глобальных и локальных
полей, компонентов и версий — для них используй закрытие резолюцией
(`issue_close`) или скрытие через UI.

**Users:** `users_get_all`, `users_search`, `user_get`, `user_get_current`

**Metadata:** `get_global_fields`, `get_issue_types`, `get_priorities`,
`get_resolutions`, `get_statuses`, `get_link_types`, `get_myself`

## Типовые сценарии — куда читать дальше

Читай **только** нужный reference, не все сразу:

- **Сбор контекста задачи (глубина 2)** — `references/gather-task-context.md`
- **Создание подзадач с артефактами** — `references/create-subtasks.md`
- **Транзиции и закрытие** — `references/transitions-and-close.md`
- **Скачивание/загрузка вложений** — `references/attachments.md`
- **Синтаксис query language** — `references/query-language.md`

## Проверка окружения (doctor)

Перед первой работой:

```
# 1. Токен валидный?
python .claude/skills/ya-tracker/scripts/tracker.py get_myself '{}'
# должен вернуть {"uid":..., "login":..., "display":..., "email":...}

# 2. Очереди видны?
python .claude/skills/ya-tracker/scripts/tracker.py queues_get_all '{"per_page":10}'
```

Если `Error 401` — токен невалидный, перечитай `config/README.md`.
Если `TOKEN=MISSING` в stderr — `.env` не найден / переменная пустая.

## Изящная деградация

- **Нет `TRACKER_TOKEN`** → скрипт выйдет с кодом 2 и сообщением
  «Fill it in .env». Исправь `.env` и запусти снова.
- **Ошибка API** (401/403/404/500) — скрипт печатает `Error <status>:
  <текст>`. Вернуть as-is (не гадать причину).
- **Нет `aiohttp` или `mcp`** → `ImportError`. Установи:
  `python -m pip install aiohttp mcp`.

## Режим совместимости: MCP

Скрипт работает и как MCP-сервер (`python tracker.py` без аргументов
→ stdio_server). Это нужно только если в `.mcp.json` есть запись
`ya-tracker`; в обычном режиме скилл использует CLI.
