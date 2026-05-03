# Вложения: скачивание и загрузка

## Список вложений

```
python scripts/tracker.py issue_get_attachments '{"issue_key":"DE-1569"}'
```

Вернёт массив с полями: `id`, `name`, `size`, `mimetype`, `content_url`,
`author`, `created`.

## Скачивание одного файла

Минимальный вызов — только `issue_key` и `attachment_id`:

```
python scripts/tracker.py issue_download_attachment '{
  "issue_key": "DE-1569",
  "attachment_id": 12345
}'
```

`filename` опционален — берётся из API metadata, если не передан.
`save_dir` опционален — путь куда положить файл. **`save_path` принимается как alias** к `save_dir` (обратная совместимость с интуитивным именованием).

Полный вызов с переопределениями:

```
python scripts/tracker.py issue_download_attachment '{
  "issue_key": "DE-1569",
  "attachment_id": 12345,
  "filename": "TRD.pdf",
  "save_dir": "downloads/DE-1569",
  "overwrite": false
}'
```

**Куда сохраняется** (приоритет):
1. `save_dir/<filename>` — если `save_dir` (или `save_path`) передан.
2. `<DOWNLOAD_DIR>/<issue_key>/<filename>` — fallback.

`DOWNLOAD_DIR` — из `.env` (`TRACKER_DOWNLOAD_DIR`), по умолчанию
`./downloads` относительно CWD.

**Поведение на коллизию имени файла** (default):
- Если файл с таким именем уже есть — auto-suffix: `TRD.pdf` → `TRD_2.pdf` → `TRD_3.pdf` …
- В ответе появляется флаг `"renamed": true`, а `name`/`downloaded` указывают на фактический путь.
- Чтобы перезаписать существующий файл — передать `"overwrite": true`.

Вернёт:
```json
{"downloaded": "C:\\...\\downloads\\DE-1569\\TRD.pdf", "size": 524288, "name": "TRD.pdf", "renamed": false}
```

## Скачивание ВСЕХ вложений одним вызовом

```
python scripts/tracker.py issue_download_all_attachments '{
  "issue_key": "DE-1569",
  "save_dir": "downloads/DE-1569"
}'
```

Параллельно скачивает все вложения. Возвращает:
```json
{
  "downloaded": [{"id": "123", "name": "INTAKE.md", "path": "...", "size": 24136, "renamed": false}, ...],
  "failed": [],
  "count": 9, "total": 9,
  "save_dir": "downloads/DE-1569"
}
```

`save_dir` опционален — fallback на `<DOWNLOAD_DIR>/<issue_key>/`. `save_path` принимается как alias.

`overwrite` (default `false`): на коллизию имени файла — auto-suffix `_2`, `_3`, …; с `true` — silent overwrite. Если в одной задаче встречаются несколько вложений с одинаковым `name` — все они скачаются (с авто-суффиксами), а не затрут друг друга.

## Загрузка файла

`file_path` — абсолютный путь.

```
python scripts/tracker.py issue_upload_attachment '{
  "issue_key": "DE-1569",
  "file_path": "/abs/path/to/file.md",
  "filename": "file.md"
}'
```

- `file_path` — абсолютный путь на диске.
- `filename` — необязательно, по умолчанию basename.
- Успех: вернёт метаданные загруженного вложения.

## Удаление вложения

```
python scripts/tracker.py issue_delete_attachment '{
  "issue_key": "DE-1569",
  "attachment_id": 12345
}'
```

- Успех (HTTP 204): `Attachment 12345 deleted from DE-1569`.
- 404 — вложение уже отсутствует или нет прав.
- Скачанные локальные копии не трогаются — удаление только на стороне
  Трекера.

Получить `attachment_id` — через `issue_get_attachments` (поле `id`).

## Типичные MIME-типы

- `application/pdf`
- `text/markdown`, `text/plain`
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document` — .docx
- `image/png`, `image/jpeg`
- `application/zip`

## Размер вложения

В `issue_get_attachments` есть поле `size` (в байтах) — для оценки
до скачивания.
