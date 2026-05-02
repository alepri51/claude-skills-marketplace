# Чтение задачи

Скилл возвращает данные задачи. Дальнейшие действия — на стороне вызывающего.

## Базовое чтение

```
python scripts/tracker.py issue_get             '{"issue_key":"DE-1569"}'
python scripts/tracker.py issue_get_links       '{"issue_key":"DE-1569"}'
python scripts/tracker.py issue_get_comments    '{"issue_key":"DE-1569"}'
python scripts/tracker.py issue_get_attachments '{"issue_key":"DE-1569"}'
python scripts/tracker.py issue_get_transitions '{"issue_key":"DE-1569"}'
python scripts/tracker.py issue_get_checklist   '{"issue_key":"DE-1569"}'
python scripts/tracker.py issue_get_worklogs    '{"issue_key":"DE-1569"}'
```

## Скачивание вложений

Одно вложение:

```
python scripts/tracker.py issue_download_attachment '{
  "issue_key": "DE-1569",
  "attachment_id": 12345,
  "filename": "TRD.pdf",
  "save_dir": "downloads/DE-1569"
}'
```

Все вложения параллельно (filename определяется автоматически):

```
python scripts/tracker.py issue_download_all_attachments '{
  "issue_key": "DE-1569",
  "save_dir": "downloads/DE-1569"
}'
```

## issue_get без описания

Если описание не нужно (например, читаешь много задач батчем):

```
python scripts/tracker.py issue_get '{"issue_key":"DE-1742","include_description":false}'
```
