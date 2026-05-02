---
name: ya-wiki
description: >
  CLI для Яндекс Вики: чтение и запись страниц, подстраниц, вложений,
  комментариев, динамических таблиц, версий, восстановление удалённых.
  Используй этот скилл всегда, когда нужно что-то сделать в Вики:
  собрать страницу с контентом и комментариями, обойти дерево
  подстраниц, создать новую страницу, прикрепить отчёт, оставить
  комментарий, восстановить удалённую страницу. Триггер-фразы: «собери
  страницу users/foo из вики», «дай содержимое вики /team/handbook»,
  «обойди подстраницы /team/onboarding», «создай страницу sandbox/test
  с заголовком X», «обнови содержимое вики страницы id 123», «прикрепи
  REPORT.md к странице вики», «скачай файл с вики /team/foo/.files/x.pdf»,
  «оставь комментарий на странице id 555», «восстанови удалённую страницу
  по recovery_token». Все 25+ операций Wiki API v1 доступны через один CLI.
  Токен из корневого .env (YANDEX_TOKEN).
compatibility: >
  Требуется Python 3.10+ и пакеты: aiohttp, mcp. Установка:
    python -m pip install aiohttp mcp
  Креденшлы: YANDEX_TOKEN (scope wiki:read и/или wiki:write) +
  (YANDEX_CLOUD_ORG_ID или YANDEX_ORG_ID) в корневом .env.
  Проверка: python scripts/wiki.py users_get_current '{}'
---

# ya-wiki

CLI для Yandex Wiki API v1. Двадцать пять+ инструментов одной командой.

## Когда этот скилл полезен

Типичные запросы:

- «Собери страницу users/foo» → `page_get` с `fields=content,breadcrumbs,attributes`,
  потом `page_get_comments` и `page_get_attachments` (см. `references/gather-page-context.md`)
- «Обойди подстраницы /team» → `page_get_subpages_by_slug`
- «Создай страницу sandbox/test» → `page_create` (см. `references/create-pages.md`)
- «Прикрепи REPORT.md к странице id=123» → `page_upload_attachment`
  (полный pipeline: session → upload → finish → attach)
- «Скачай файл x.pdf со страницы /team/foo» → `attachment_download_by_slug`
- «Оставь комментарий на странице id=555» → `page_add_comment`
- «Восстанови удалённую страницу id=999» → `page_restore` с recovery_token
  (запоминай recovery_token из `page_delete`!)

## Как вызывать — через CLI

Общий формат:

```
python .claude/skills/ya-wiki/scripts/wiki.py <tool> '<json_args>'
```

Список всех инструментов:

```
python .claude/skills/ya-wiki/scripts/wiki.py list-tools
```

Примеры:

```
# получить страницу со всеми блоками
python .claude/skills/ya-wiki/scripts/wiki.py \
  page_get '{"slug":"users/foo/bar","fields":"content,breadcrumbs,attributes"}'

# дерево подстраниц по slug (cursor-paginated)
python .claude/skills/ya-wiki/scripts/wiki.py \
  page_get_subpages_by_slug '{"slug":"team","page_size":100}'

# создать страницу
python .claude/skills/ya-wiki/scripts/wiki.py \
  page_create '{"slug":"sandbox/test","title":"Test","content":"hello","is_silent":true}'

# обновить страницу по id
python .claude/skills/ya-wiki/scripts/wiki.py \
  page_update '{"page_id":12345,"content":"new content"}'

# приложить файл (вся pipeline 4-х шагов внутри одной команды)
python .claude/skills/ya-wiki/scripts/wiki.py \
  page_upload_attachment '{"page_id":12345,"file_path":"C:/tmp/REPORT.md"}'

# скачать файл по slug+name
python .claude/skills/ya-wiki/scripts/wiki.py \
  attachment_download_by_slug '{"slug":"users/foo/bar","filename":"x.pdf"}'

# удалить страницу (запомни recovery_token!)
python .claude/skills/ya-wiki/scripts/wiki.py \
  page_delete '{"page_id":12345}'
# → {"deleted": 12345, "recovery_token": "uuid4-..."}

# восстановить
python .claude/skills/ya-wiki/scripts/wiki.py \
  page_restore '{"page_id":12345,"recovery_token":"uuid4-..."}'
```

## Полный набор инструментов

**Pages — чтение:**
- `page_get` (по slug), `page_get_by_id`
- `page_get_subpages` (по id), `page_get_subpages_by_slug`
- `page_get_url` (построить web-URL из slug)

**Pages — запись:**
- `page_create`, `page_update`
- `page_delete` (возвращает recovery_token), `page_restore`
- `page_clone` (копирование), `page_append_content`

**Attachments:**
- `page_get_attachments`
- `attachment_download_by_id`, `attachment_download_by_slug`
- `page_upload_attachment` (полный pipeline в одной команде)
- `attachment_delete`

**Page resources:** `page_get_grids` (динамические таблицы)

**Comments:** `page_get_comments`, `page_add_comment`, `comment_delete`,
`page_get_comment_thread`

**Users:** `users_get_current`, `get_myself`

**Upload sessions (low-level — нужны редко):**
`upload_session_create`, `upload_session_get`, `upload_session_finish`, `upload_session_abort`

**Operations:** `operation_get` (статус async-операций — clone/restore)

## Типовые сценарии — куда читать дальше

Читай **только** нужный reference, не все сразу:

- **Сбор контекста страницы (контент + комменты + вложения)** — `references/gather-page-context.md`
- **Создание страниц и подстраниц** — `references/create-pages.md`
- **Скачивание/загрузка вложений** — `references/attachments.md`
- **Обход дерева, slug vs id** — `references/search-and-list.md`
- **Комментарии и восстановление** — `references/comments-and-restore.md`

## Идентификаторы: slug vs id

Wiki поддерживает оба:
- **slug** — человекочитаемый путь, `users/foo/bar` или `team/handbook`.
  Используй для `page_get`, `page_get_subpages_by_slug`, `attachment_download_by_slug`.
- **id** — числовой идентификатор (целое число). Нужен для большинства write-операций
  (`page_update`, `page_delete`, `page_clone`, `page_append_content`,
  `page_get_attachments`, `page_upload_attachment`, `page_get_comments`).

Чтобы получить id по slug — вызови `page_get` и возьми поле `id`.

## Проверка окружения (doctor)

Перед первой работой:

```
# 1. Токен валидный?
python .claude/skills/ya-wiki/scripts/wiki.py users_get_current '{}'
# должен вернуть {"username":..., "uid":..., "dir_id":..., ...}

# 2. Доступ к организации?
python .claude/skills/ya-wiki/scripts/wiki.py page_get_subpages_by_slug '{"slug":"","page_size":5}'
# вернёт корневое дерево или Error 403, если нет доступа
```

Если `Error 401` — токен невалидный или у него нет scope `wiki:read`.
Если `Error 403` — токен валидный, но нет доступа к организации
(проверь `YANDEX_ORG_ID` / `YANDEX_CLOUD_ORG_ID`).
Если `TOKEN=MISSING` в stderr при запуске — `.env` не найден или
переменная пустая.

## Изящная деградация

- **Нет `YANDEX_TOKEN`** → скрипт выйдет с кодом 2 и сообщением
  «Fill it in .env». Исправь `.env` и запусти снова.
- **Ошибка API** (401/403/404/500) — скрипт печатает `Error <status>:
  <текст>`. Передать оркестратору as-is (не гадать причину).
- **Нет `aiohttp` или `mcp`** → `ImportError`. Установи:
  `python -m pip install aiohttp mcp`.

## Режим совместимости: MCP

Скрипт работает и как MCP-сервер (`python wiki.py` без аргументов
→ stdio_server). Это нужно только если в `.mcp.json` есть запись
`ya-wiki`; в обычном режиме скилл использует CLI.

## Совместимость с ya-tracker

Использует те же общие переменные окружения: `YANDEX_TOKEN`,
`YANDEX_ORG_ID`/`YANDEX_CLOUD_ORG_ID`. Один OAuth-токен с двумя
scope (`tracker:write` + `wiki:write`) покрывает оба скилла.
