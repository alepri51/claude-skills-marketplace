# Обход дерева страниц и идентификаторы

## slug vs id — когда что

| Операция | По slug | По id |
|---|---|---|
| Чтение страницы | `page_get` | `page_get_by_id` |
| Подстраницы | `page_get_subpages_by_slug` | `page_get_subpages` |
| Скачать вложение | `attachment_download_by_slug` | `attachment_download_by_id` |
| Update / delete / clone / append-content | — | только id |
| Comments / attachments list | — | только id |

**Правило:** read-only по slug удобнее (slug стабилен и читаемый), все
write-операции и работа с вложениями/комментами — по числовому id.

Чтобы получить id из slug — `page_get` без fields:

```
python scripts/wiki.py page_get '{"slug":"team/handbook"}' | jq -r '.id'
```

## Обход всего дерева

`page_get_subpages_by_slug` возвращает **все уровни потомков** одной
страницы (не только прямых детей). Cursor-paginated.

Полный обход:

```bash
SLUG="team"
CURSOR=""
while :; do
  ARGS="{\"slug\":\"$SLUG\",\"page_size\":100"
  [ -n "$CURSOR" ] && ARGS="$ARGS,\"cursor\":\"$CURSOR\""
  ARGS="$ARGS}"
  RESP=$(python scripts/wiki.py page_get_subpages_by_slug "$ARGS")
  echo "$RESP" | jq -r '.results[] | "\(.id)\t\(.slug)"'
  CURSOR=$(echo "$RESP" | jq -r '.next_cursor // empty')
  [ -z "$CURSOR" ] && break
done
```

## Web-URL страницы

```
python scripts/wiki.py page_get_url '{"slug":"team/handbook"}'
# → https://wiki.yandex.ru/team/handbook
```

URL формируется на стороне CLI, не запрашивая API. Удобно когда нужно
дать ссылку человеку.

## Идентификаторы в breadcrumbs

При запросе `page_get` с `fields=breadcrumbs` каждый элемент крошек
содержит `id`, `slug`, `title`. Так можно построить полный путь:

```
python scripts/wiki.py page_get '{
  "slug": "team/handbook/onboarding/checklist",
  "fields": "breadcrumbs"
}' | jq -r '.breadcrumbs[] | "\(.slug) → \(.title)"'
```

## Поиск по содержимому?

Wiki API v1 **не предоставляет полнотекстовый поиск** через публичный
endpoint. Поиск работает в UI Вики, но через API — нет.

Альтернативы:
- Скачать содержимое поддерева через `page_get_subpages_by_slug` +
  `page_get` для каждой страницы и грепать локально.
- Использовать `page_get` со знанием slug'а (если он известен).
