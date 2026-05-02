# ClickHouse — особенности

## Список таблиц

```
python scripts/db.py db_tables '{"pattern":"%"}' --connection <name>
```

## Схема

`db_schema` возвращает `{field, type}` через `DESCRIBE TABLE`.
Индексы и движок (MergeTree/ReplicatedMergeTree) — через:

```sql
SHOW CREATE TABLE events;
SELECT * FROM system.tables WHERE name='events';
SELECT * FROM system.parts WHERE table='events' LIMIT 10;
```

## Протокол

Используется `clickhouse_driver` с native TCP (порт 9000 по умолчанию).
Если в `.env` указан HTTP-порт (8123) — не заработает.

## Размер и объём

```sql
SELECT table, formatReadableSize(sum(bytes_on_disk)) AS size
FROM system.parts WHERE active GROUP BY table ORDER BY sum(bytes_on_disk) DESC;
```

## Ограничения

Пишущие запросы блокируются. `INSERT/ALTER/TRUNCATE/OPTIMIZE` — не
проходят (whitelist: SELECT, EXPLAIN, SHOW, DESCRIBE).
