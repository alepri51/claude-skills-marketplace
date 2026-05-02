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
`save_dir` опционален — путь куда положить файл.

Полный вызов с переопределениями:

```
python scripts/tracker.py issue_download_attachment '{
  "issue_key": "DE-1569",
  "attachment_id": 12345,
  "filename": "TRD.pdf",
  "save_dir": "downloads/DE-1569"
}'
```

**Куда сохраняется** (приоритет):
1. `save_dir/<filename>` — если `save_dir` передан.
2. `<DOWNLOAD_DIR>/<issue_key>/<filename>` — fallback.

`DOWNLOAD_DIR` — из `.env` (`TRACKER_DOWNLOAD_DIR`), по умолчанию
`./downloads` относительно CWD.

Вернёт:
```json
{"downloaded": "C:\\...\\downloads\\DE-1569\\TRD.pdf", "size": 524288, "name": "TRD.pdf"}
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
  "downloaded": [{"id": "123", "name": "INTAKE.md", "path": "...", "size": 24136}, ...],
  "failed": [],
  "count": 9, "total": 9,
  "save_dir": "downloads/DE-1569"
}
```

`save_dir` опционален — fallback на `<DOWNLOAD_DIR>/<issue_key>/`.

## Загрузка файла

**Абсолютный путь** обязательно (см. CLAUDE.md §9):

```
python scripts/tracker.py issue_upload_attachment '{
  "issue_key": "DE-1569",
  "file_path": "C:/projects/AI_AGENTS/o-a-v1/.planning/phases/1/PLAN.md",
  "filename": "1-1-PLAN.md"
}'
```

- `file_path` — абсолютный путь на диске.
- `filename` — необязательно, по умолчанию basename.
- Успех: вернёт метаданные загруженного вложения.

## Важно: ветка задачи — до скачивания

Скачанные вложения попадают в файловую систему (в `<DOWNLOAD_DIR>`).
Если они попадут в `main` — засорят шаблонную ветку.

**Правило:** создать ветку задачи `git checkout -b tasks/{issue_key}`
**до** первого `issue_download_attachment`. См. CLAUDE.md §6.1.

## Типичные MIME-типы

- `application/pdf` — читать через `Read file_path`, PDF поддерживается
- `text/markdown`, `text/plain` — `Read file_path`
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  — .docx, конвертировать при необходимости
- `image/png`, `image/jpeg` — `Read file_path` (мультимодально)
- `application/zip` — распаковывать перед чтением

## Если вложение большое

В `issue_get_attachments` есть поле `size` (в байтах). Если файл
огромный (десятки MB) — спросить у аналитика, нужно ли его читать
целиком, или можно работать со ссылкой/выжимкой.
