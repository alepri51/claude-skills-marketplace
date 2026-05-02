# Создание задач, связей и загрузка вложений

## issue_create

```
python scripts/tracker.py issue_create '{
  "queue": "DE",
  "summary": "Краткое название",
  "description": "...текст...",
  "parent": "DE-1569",
  "tags": ["tag1", "tag2"]
}'
```

Поля:
- `queue` — ключ очереди.
- `summary` — заголовок.
- `description` — тело (опционально).
- `parent` — родительская задача (опционально).
- `tags` — массив тегов (опционально).
- `assignee` — логин исполнителя или `null` для обнуления (опционально).

Если очередь имеет дефолтного исполнителя и нужно создать без него —
после `issue_create` сразу:

```
python scripts/tracker.py issue_update '{"issue_key":"DE-1600","assignee":null}'
```

## issue_create_link

```
python scripts/tracker.py issue_create_link '{
  "issue_key": "DE-1601",
  "target_issue": "DE-1600",
  "relationship": "depends on"
}'
```

Типы связей: `relates`, `depends on`, `is dependent by`,
`is subtask for`, `is parent task for`, `duplicates`,
`is duplicated by`, `is epic of`, `has epic`.

## issue_upload_attachment

`file_path` — абсолютный путь.

```
python scripts/tracker.py issue_upload_attachment '{
  "issue_key": "DE-1600",
  "file_path": "/abs/path/to/file.md",
  "filename": "file.md"
}'
```
