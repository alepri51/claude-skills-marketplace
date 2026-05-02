# MySQL — особенности

## Список таблиц

```
python scripts/db.py db_tables '{"pattern":"%"}' --connection <name>
```

`pattern` — LIKE-шаблон: `user_%`, `%_log`, `%`.

## Схема таблицы

```
python scripts/db.py db_schema '{"table":"users"}' --connection <name>
```

Возвращает три блока:
- `columns` — `DESCRIBE`: field, type, null, key, default
- `indexes` — группировка `SHOW INDEX` по `Key_name`, упорядочено по
  `Seq_in_index`. Для каждого: `name`, `unique`, `type`, `columns`,
  `cardinality`.
- `stats` — `information_schema.tables`: `rows_estimate`, `data_mb`,
  `index_mb`. `rows_estimate` — оценка MySQL, может сильно
  расходиться с реальным `COUNT(*)` на больших таблицах.

## Read-only запросы

`db_query` разрешает только `SELECT`, `EXPLAIN`, `SHOW`, `DESCRIBE`,
`DESC`. Любой DML/DDL (`INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/TRUNCATE`)
блокируется на уровне скрипта.

`SELECT` без `LIMIT` автоматически получает `LIMIT 200`. Чтобы выбрать
больше — укажи `LIMIT N` явно.

## EXPLAIN для планов запросов

```
python scripts/db.py db_query '{"sql":"EXPLAIN SELECT * FROM users WHERE email=?"}' --connection <name>
```

EXPLAIN/SHOW пропускаются без автоподстановки LIMIT — они и так
возвращают небольшой объём.

## Объём данных

Оценка `rows_estimate` быстрая, но неточная. Для точного числа
строк — `SELECT COUNT(*) FROM <table>` (помнить про LIMIT 200 —
результат влезет в одну строку).
