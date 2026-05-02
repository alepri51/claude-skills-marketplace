# MongoDB — особенности

## Коллекции

```
python scripts/db.py db_tables '{"pattern":"%"}' --connection <name>
```

`%` → `.*` (regex). Фильтр клиентский, не серверный.

## Схема (семплированием)

```
python scripts/db.py db_schema '{"table":"users"}' --connection <name>
```

Mongo — schema-less. `db_schema` берёт случайный семпл из **10**
документов и возвращает объединённое множество полей с их типами
(`str`, `int`, `dict`, `list`, `ObjectId`…). На редкие поля может
не попасть — это нормально.

Для глубокого анализа можно расширить семпл вручную:

```json
{
  "collection": "users",
  "pipeline": [
    {"$sample": {"size": 100}},
    {"$project": {"_id": 0}}
  ]
}
```

## Запросы — JSON, не SQL

`db_query` принимает JSON вида:

```
python scripts/db.py db_query '{"sql":"{\"collection\":\"users\",\"pipeline\":[{\"$match\":{\"status\":\"active\"}},{\"$limit\":10}]}"}' --connection <name>
```

(`sql` — это строка, но внутри JSON aggregate-pipeline.)

Возвращается максимум 200 документов. Добавляй `$limit` в конец
pipeline для точного контроля.

## Read-only

Блокировки на стороне клиента нет (в отличие от SQL-бэкендов).
Не вызывай `$out`, `$merge`, `$function`, `$unsetField` и т.д. —
они могут писать в БД. Для исследования используй только
`$match`, `$project`, `$group`, `$lookup`, `$sort`, `$limit`,
`$skip`, `$unwind`, `$sample`, `$count`, `$facet`.
