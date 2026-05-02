# Комментарии и восстановление страниц

## Комментарии — чтение

```
python scripts/wiki.py page_get_comments '{
  "page_id": 12345,
  "page_size": 50,
  "order_direction": "asc",
  "status_filter": "unresolved"
}'
```

Возвращает массив `results` с полями: `id`, `body`, `author`, `created_at`,
`thread_id`, `parent_id`, `resolved`, `is_deleted`. Cursor-paginated.

Для нитки (треда):
```
python scripts/wiki.py page_get_comment_thread '{
  "page_id": 12345, "thread_id": 67
}'
```

## Добавить комментарий

```
python scripts/wiki.py page_add_comment '{
  "page_id": 12345,
  "body": "Текст комментария"
}'
```

Ответ на конкретный комментарий:
```
python scripts/wiki.py page_add_comment '{
  "page_id": 12345,
  "body": "Согласен",
  "parent_id": 333
}'
```

## Удалить комментарий

```
python scripts/wiki.py comment_delete '{
  "page_id": 12345, "comment_id": 333
}'
```

API не возвращает 204 — отдаёт 200 с обновлённым `comments_count`. Скрипт
оборачивает это в `{deleted, page_id, result}`.

## Удаление страницы — recovery_token

`page_delete` возвращает не только подтверждение, но и `recovery_token`:

```
python scripts/wiki.py page_delete '{"page_id": 12345}'
# → {"deleted": 12345, "recovery_token": "1c5e3a0a-2b4f-4f8c-a8b1-..."}
```

**Сохрани этот токен** — без него восстановить страницу не получится.
Токен действителен ограниченное время (обычно несколько суток).

Не печатать в открытые логи — токен даёт право на восстановление.

## Восстановление

```
python scripts/wiki.py page_restore '{
  "page_id": 12345,
  "recovery_token": "1c5e3a0a-..."
}'
```

Если токен валиден и страница ещё восстановима — вернёт восстановленную
страницу. Иначе `Error 404` или `410 Gone`.

Восстановление может быть асинхронным — в ответе может быть `operation_id`.
Тогда проверь статус:
```
python scripts/wiki.py operation_get '{"operation_id": "<op_id>"}'
# повторяй пока status не станет 'finished' или 'failed'
```

## Сценарий: рискованное удаление

Перед удалением страницы с подстраницами:

```bash
PID=12345

# 1. Снять структуру поддерева
python scripts/wiki.py page_get_subpages '{"page_id":'"$PID"',"include_self":true,"page_size":100}' \
  > /tmp/wiki-tree-$PID.json

# 2. Удалить
RESP=$(python scripts/wiki.py page_delete '{"page_id":'"$PID"'}')
echo "$RESP" > /tmp/wiki-recovery-$PID.json
TOKEN=$(echo "$RESP" | jq -r '.recovery_token')
echo "Recovery token saved: $TOKEN"

# 3. Если что-то пошло не так:
python scripts/wiki.py page_restore '{"page_id":'"$PID"',"recovery_token":"'"$TOKEN"'"}'
```
