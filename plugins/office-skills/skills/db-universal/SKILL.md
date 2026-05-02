---
name: db-universal
description: >
  Инспектор БД — MySQL, PostgreSQL, ClickHouse, Redis, MongoDB. Используй этот
  скилл всегда, когда нужно прочитать структуру БД проекта: посмотреть список
  таблиц/коллекций, схему колонок и индексов, оценить объём данных, выполнить
  read-only SELECT/EXPLAIN/SHOW, достать ключ из Redis, агрегировать Mongo.
  Триггер-сценарии: «какие таблицы в parsing-dev», «покажи схему users»,
  «сколько строк в events», «какие индексы на заказах», «EXPLAIN для запроса»,
  «проверь, есть ли поле X в БД», «исследуй БД сервиса bnmap». Скилл НЕ пишет
  в БД — разрешены только SELECT/EXPLAIN/SHOW/DESCRIBE; любой DML/DDL
  блокируется. Подключения к именованным БД (db-parsing-dev, db-bnmap-prod
  и т.д.) берутся из config/connections.json, креденшлы — из корневого .env.
compatibility: >
  Требуется Python 3.10+ и пакеты под нужные движки:
    aiohttp, python-dotenv, mcp
    mysql-connector-python (MySQL)
    psycopg2-binary (PostgreSQL)
    clickhouse-driver (ClickHouse)
    redis (Redis)
    pymongo (MongoDB)
  Установить всё сразу:
    python -m pip install aiohttp python-dotenv mcp mysql-connector-python \
      psycopg2-binary clickhouse-driver redis pymongo
---

# db-universal

Универсальный инспектор баз данных для MySQL, PostgreSQL, ClickHouse,
Redis и MongoDB. Один CLI — пять бэкендов — единый набор команд.

## Когда этот скилл полезен

Типичные запросы аналитика/оркестратора:

- «Какие таблицы в базе `parsing-dev`?»
- «Покажи схему таблицы `deals` — поля, индексы, размер.»
- «Сколько строк в `events`?»
- «EXPLAIN этого запроса — используется ли индекс?»
- «Есть ли колонка `email` в таблице `users`?»
- «Проверь, что нет полей `deleted_at` на проде в `bnmap`.»
- «Достань из Redis ключ `session:42` и покажи, что там лежит.»
- «Агрегат по Mongo-коллекции `leads`: сгруппируй по `source`.»

## Что умеет (5 инструментов)

| Инструмент   | Что делает                                                    |
|--------------|---------------------------------------------------------------|
| `db_tables`  | Список таблиц/коллекций по LIKE-шаблону                       |
| `db_schema`  | Колонки + индексы + размер (MySQL), колонки (PG/CH/Mongo)     |
| `db_query`   | Read-only запрос: SELECT/EXPLAIN/SHOW/DESCRIBE или Mongo JSON |
| `db_keys`    | Redis: ключи по glob-шаблону                                  |
| `db_get`     | Redis: значение ключа (string/hash/list/set/zset)             |

Специфика каждого движка — в `references/<engine>.md` (читай только
нужный, не все сразу).

## Как вызывать — через CLI

Общий формат:

```
python .claude/skills/db-universal/scripts/db.py <tool> '<json_args>' --connection <name>
```

- `<tool>` — одно из `db_tables`, `db_schema`, `db_query`, `db_keys`, `db_get`.
- `<json_args>` — JSON со входами инструмента (`pattern`, `table`, `sql`, `key`).
- `--connection <name>` — именованное подключение из
  `config/connections.json` (см. список подключений командой
  `python .claude/skills/db-universal/scripts/db.py list-connections`).

Примеры:

```
# список таблиц parsing-dev
python .claude/skills/db-universal/scripts/db.py \
  db_tables '{"pattern":"%"}' --connection db-parsing-dev

# схема таблицы users в bnmap-prod
python .claude/skills/db-universal/scripts/db.py \
  db_schema '{"table":"users"}' --connection db-bnmap-prod

# count строк
python .claude/skills/db-universal/scripts/db.py \
  db_query '{"sql":"SELECT COUNT(*) AS c FROM users"}' --connection db-parsing-dev

# план запроса
python .claude/skills/db-universal/scripts/db.py \
  db_query '{"sql":"EXPLAIN SELECT * FROM users WHERE email=\"x@y\""}' --connection db-parsing-dev
```

## Безопасность: read-only

- `db_query` разрешает только `SELECT`, `EXPLAIN`, `SHOW`, `DESCRIBE`,
  `DESC`. Всё остальное возвращает ошибку на уровне скрипта — до
  реального запроса к БД.
- `SELECT` без `LIMIT` получает авто-`LIMIT 200` (чтобы случайно не
  вытянуть миллион строк). Нужен другой лимит — указать явно.
- Mongo-клиент read-only не умеет форсить — избегай операторов-мутаторов
  (`$out`, `$merge`, `$function`). Подробнее: `references/mongo.md`.

## Сценарий «исследуй БД сервиса X»

Последовательность, которая закрывает 90% задач исследования:

1. **Определить подключение** — `list-connections`, сверить с тем, что
   в задаче/документации сервиса. Если нужного подключения нет —
   добавить в `config/connections.json` по инструкции в `config/README.md`.
2. **Обзор таблиц** — `db_tables '{"pattern":"%"}' --connection <name>`.
3. **Схемы ключевых таблиц** — `db_schema` по каждой релевантной таблице.
   Для MySQL сразу видны индексы и размер.
4. **Оценка объёмов** — `SELECT COUNT(*)` на критичных таблицах или
   `stats.rows_estimate` из `db_schema` (для MySQL).
5. **Проверка запросов** — `EXPLAIN` для тяжёлых запросов, чтобы
   убедиться, что используются индексы.

Результаты положить в `.planning/codebase/OVERVIEW.md` (или там,
куда просит текущий workflow).

## Движки: куда читать дальше

Читай только тот файл, который нужен сейчас:

- `references/mysql.md` — DESCRIBE/SHOW INDEX, rows_estimate, EXPLAIN
- `references/postgres.md` — схема `public`, pg_indexes, pg_size_pretty
- `references/clickhouse.md` — DESCRIBE TABLE, system.parts, native TCP
- `references/redis.md` — KEYS blocking, типы значений, database index
- `references/mongo.md` — семплирование схемы, aggregate pipeline

## Изящная деградация

Если:

- **нет нужного подключения в `connections.json`** → скрипт вернёт
  ошибку с именем. Добавь подключение по инструкции в
  `config/README.md`.
- **нет переменных в `.env`** → переменная `${X}` уйдёт в драйвер
  как есть и тот выдаст TCP-ошибку. Проверь `.env` и перезапусти.
- **не установлен драйвер** (например `psycopg2`) → `ImportError` с
  именем пакета. Установи пакет из `compatibility` выше.

В любом из этих случаев сообщи аналитику точным текстом ошибки и
**жди**, не гадай параметры.

## Режим совместимости: MCP

Скрипт работает и как MCP-сервер (`python db.py` без аргументов →
stdio_server). Это нужно только если в `.mcp.json` есть запись
`db-universal`; в обычном режиме скилл использует CLI.
