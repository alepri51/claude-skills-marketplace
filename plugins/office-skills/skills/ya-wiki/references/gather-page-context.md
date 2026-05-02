# Сбор контекста страницы Yandex Wiki

Когда оркестратор просит «собери страницу X» или «дай мне контекст по странице
вики», под этим обычно понимается: метаданные + контент + breadcrumbs +
комментарии + вложения. Wiki API возвращает большую часть этого по запросу
полей `fields=...`, но комментарии и вложения нужны отдельными запросами.

## Шаг 1. Метаданные + контент по slug

```
python scripts/wiki.py page_get '{
  "slug": "users/foo/bar",
  "fields": "content,breadcrumbs,attributes"
}'
```

Возвращает: `id`, `slug`, `title`, `page_type`, `created_at`, `modified_at`,
`author`, `comments_count`, `breadcrumbs`, `content`.

Запомни поле `id` — оно нужно для следующих шагов.

## Шаг 2. Комментарии (если `comments_count` > 0)

```
python scripts/wiki.py page_get_comments '{
  "page_id": <id>,
  "page_size": 100,
  "order_direction": "asc"
}'
```

Если ответ содержит `next_cursor` — повтори запрос с `cursor: "<value>"` для
следующей страницы. Если нужен только нерешённый — `status_filter: "unresolved"`.

## Шаг 3. Вложения

```
python scripts/wiki.py page_get_attachments '{"page_id": <id>, "page_size": 100}'
```

Получишь массив с `id`, `name`, `size`, `mimetype`, `download_url`.

## Шаг 4. Скачать ключевые вложения (опционально)

Если нужно посмотреть содержимое файла — `attachment_download_by_id`:

```
python scripts/wiki.py attachment_download_by_id '{
  "page_id": <id>, "file_id": <attachment.id>, "filename": "<attachment.name>"
}'
```

Файл сохранится в `WIKI_DOWNLOAD_DIR/<page_id>/<filename>` (по умолчанию
`downloads/<page_id>/<filename>` от текущей рабочей директории).

## Шаг 5. Подстраницы (если нужен обход иерархии)

```
python scripts/wiki.py page_get_subpages_by_slug '{
  "slug": "users/foo/bar", "page_size": 100
}'
```

Возвращает плоский список **всех уровней** потомков (`results`), с
`next_cursor`/`prev_cursor`. Это **не** только прямые дети.

## Что НЕ делать

- Не запрашивай `fields=content` для каждой подстраницы при обходе —
  будет десятки тысяч запросов. Сначала получи список, потом точечно
  читай нужные.
- Не ходи по URL `https://wiki.yandex.ru/...` через WebFetch — это
  публичная страница, требующая логина. Используй API.
- `page_get` без `fields` вернёт только `id`, `slug`, `title`, `page_type` —
  без контента. Всегда указывай `fields` явно.
