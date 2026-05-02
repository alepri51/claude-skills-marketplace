# Вложения Yandex Wiki

В отличие от Tracker, Wiki **не использует multipart/form-data** для загрузки.
Вместо этого — pipeline из 4 шагов через upload sessions. Скилл `ya-wiki`
скрывает это в одной команде `page_upload_attachment`.

## Загрузка файла

```
python scripts/wiki.py page_upload_attachment '{
  "page_id": 12345,
  "file_path": "C:/tmp/REPORT.md"
}'
```

Что происходит внутри:
1. `POST /v1/upload_sessions` с `{file_name, file_size}` → получает `session_id` (UUID4).
2. `PUT /v1/upload_sessions/{session_id}/upload_part?part_number=1` с `Content-Type: application/octet-stream` — заливает данные. Для файлов меньше 8 MB — одной частью; для больших — несколькими.
3. `POST /v1/upload_sessions/{session_id}/finish` — завершает.
4. `POST /v1/pages/{page_id}/attachments` с `{upload_sessions: [session_id]}` — привязывает.

Возвращает `{uploaded, size, session_id, attachments: [...]}`. В `attachments`
объект с `id` — он понадобится для удаления или скачивания по id.

## Параметры

- `filename` (опц.) — переопределить имя на стороне Wiki. По умолчанию —
  `Path(file_path).name`.
- Поддерживаются файлы любого размера. Скилл сам режет на части по 8 MB.

## Скачивание

### По page_id + file_id (нужны оба)

```
python scripts/wiki.py attachment_download_by_id '{
  "page_id": 12345,
  "file_id": 67890,
  "filename": "REPORT.md"
}'
```

Сохранит в `<WIKI_DOWNLOAD_DIR>/12345/REPORT.md`.

### По slug + filename

Удобно когда знаешь только URL вида `wiki.yandex.ru/users/foo/.files/x.pdf`:

```
python scripts/wiki.py attachment_download_by_slug '{
  "slug": "users/foo",
  "filename": "x.pdf"
}'
```

Скрипт автоматически склеит `<slug>/.files/<filename>` и передаст в
параметр `url` API. Сохранит в `<WIKI_DOWNLOAD_DIR>/users/foo/x.pdf`.

Опционально: `save_as` — переопределить локальное имя файла.

## Список вложений

```
python scripts/wiki.py page_get_attachments '{"page_id": 12345}'
```

Возвращает массив с `id`, `name`, `size`, `mimetype`, `download_url`,
`created_at`, `author`. Cursor-paginated (`next_cursor`).

## Удаление

```
python scripts/wiki.py attachment_delete '{
  "page_id": 12345,
  "file_id": 67890
}'
```

## DOWNLOAD_DIR

По умолчанию все скачанные файлы кладутся в `downloads/<page_id_or_slug>/<filename>`
от текущей рабочей директории. Чтобы изменить — задай `WIKI_DOWNLOAD_DIR` в `.env`:

```
WIKI_DOWNLOAD_DIR=/c/work/wiki-downloads
```

## Низкоуровневые сессии (нужны редко)

Если файл огромный (>1 GB) и хочешь параллельную загрузку — используй
`upload_session_create` / `upload_session_get` / `upload_session_finish` /
`upload_session_abort` напрямую. Загрузка частей доступна только из кода;
`PUT /upload_part` не вынесен в CLI как отдельный инструмент, потому что
он принимает бинарные данные, а CLI принимает JSON. Если нужно — расширяй
`page_upload_attachment` или используй `requests`/`aiohttp` напрямую.
