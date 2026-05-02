# PostgreSQL — особенности

## Схема 'public'

`db_tables` и `db_schema` работают только со схемой `public`. Для
других схем используй `db_query` с квалифицированными именами:

```
python scripts/db.py db_query '{"sql":"SELECT tablename FROM pg_tables WHERE schemaname=''audit''"}' --connection <name>
```

## db_schema vs MySQL

В отличие от MySQL, `db_schema` для Postgres возвращает **только
колонки** (`information_schema.columns`). Индексы и размеры нужно
спрашивать явно:

```sql
-- индексы
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'users';

-- размер
SELECT pg_size_pretty(pg_total_relation_size('users'));

-- оценка строк
SELECT reltuples::bigint AS rows FROM pg_class WHERE relname = 'users';
```

## Read-only

Те же правила, что в MySQL: только `SELECT`, `EXPLAIN`, `SHOW`,
`DESCRIBE`. Авто-LIMIT 200 для `SELECT`.

## EXPLAIN ANALYZE

`EXPLAIN ANALYZE` разрешён (начинается с `EXPLAIN`), но **реально
выполняет запрос** — для тяжёлых SELECT'ов может быть долго. На
неподтверждённых запросах используй обычный `EXPLAIN`.
