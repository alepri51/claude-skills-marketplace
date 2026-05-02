# Создание страниц в Yandex Wiki

## Формат slug

Slug — это путь страницы в иерархии Вики. Разделитель — `/`. Не начинай с `/`
и не заканчивай `/`. Примеры: `users/john/notes`, `team/onboarding`,
`sandbox/test`.

Создание страницы автоматически создаёт всех родителей в slug, если их нет.
Если slug уже занят — `Error 409`.

## Базовое создание

```
python scripts/wiki.py page_create '{
  "slug": "sandbox/test",
  "title": "Test page",
  "content": "Hello world."
}'
```

Возвращает созданную страницу с `id`, `slug`, `title`. Уведомления подписчикам
при создании родителя отправляются по умолчанию.

## Тихое создание (без уведомлений)

```
python scripts/wiki.py page_create '{
  "slug": "sandbox/test",
  "title": "Test",
  "content": "...",
  "is_silent": true
}'
```

## Возвратить полный объект (с контентом и хлебными крошками)

```
python scripts/wiki.py page_create '{
  "slug": "sandbox/test",
  "title": "Test",
  "content": "...",
  "fields": "content,breadcrumbs,attributes"
}'
```

## Содержимое: формат

Wiki принимает текст в Wiki-разметке. В `content` можно передавать:
- обычный текст (поддерживается базовая wiki-разметка: заголовки `==`, списки,
  таблицы, ссылки `((ссылка текст))`)
- многострочные блоки — экранируй переводы строк через `\n` в JSON.

Большие документы лучше **сохранить в файл и подгрузить** через bash:

```
content=$(cat REPORT.md | python -c "import json,sys;print(json.dumps(sys.stdin.read()))")
python scripts/wiki.py page_create "{
  \"slug\":\"sandbox/report\",
  \"title\":\"Report\",
  \"content\":$content
}"
```

## Обновление содержимого

`page_update` работает по `page_id`, не по slug. Получи id через `page_get`
с тем же slug:

```
python scripts/wiki.py page_get '{"slug":"sandbox/test"}' | jq -r '.id'
# затем:
python scripts/wiki.py page_update '{
  "page_id": <id>,
  "content": "новое содержимое",
  "is_silent": true
}'
```

`page_update` **полностью заменяет** контент. Чтобы дописать — `page_append_content`:

```
python scripts/wiki.py page_append_content '{
  "page_id": <id>,
  "content": "\n\n## Update\nНовая секция.",
  "location": "bottom"
}'
```

## Конфликты редактирования

Если кто-то изменил страницу между твоим `page_get` и `page_update` —
бэкенд может вернуть конфликт. Тогда используй `allow_merge: true` в
`page_update` — Wiki попробует сшить изменения автоматически.

## Удаление и восстановление

```
# удалить
python scripts/wiki.py page_delete '{"page_id": <id>}'
# → {"deleted": <id>, "recovery_token": "uuid4-..."}

# восстановить (запомни recovery_token!)
python scripts/wiki.py page_restore '{
  "page_id": <id>, "recovery_token": "uuid4-..."
}'
```

`recovery_token` действителен ограниченное время (обычно несколько дней) —
сохрани его в комментарий к задаче или в логи, если планируешь возможный откат.

## Клонирование

```
python scripts/wiki.py page_clone '{
  "page_id": <source_id>,
  "target": "sandbox/test-copy",
  "title": "Test (copy)"
}'
```

Клон может быть асинхронной операцией — в ответе будет `operation_id`. Чтобы
дождаться:

```
python scripts/wiki.py operation_get '{"operation_id": "<op_id>"}'
# повторяй пока status не станет 'finished' или 'failed'
```
