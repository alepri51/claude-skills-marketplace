# db-universal — авторизация и подключения

## Где хранятся креденшлы

**Не в скилле.** Все host/port/user/password берутся из корневого `.env`
проекта. Файл `.env` должен быть в `.gitignore` и не коммититься.

## Как устроены именованные подключения

Файл `config/connections.json` — реестр **имён** подключений.
Значения в нём — ссылки `${VAR_NAME}` на переменные из `.env`.
Сам connections.json безопасно коммитить: в нём только имена.

Пример из `.env`:

```
DB_PARSING_DEV_HOST=<host>
DB_PARSING_DEV_PORT=<port>
DB_PARSING_DEV_USER=<user>
DB_PARSING_DEV_PASSWORD=<password>
DB_PARSING_DEV_NAME=<database>
DB_PARSING_DEV_TYPE=<mysql|postgres|clickhouse|mongo|redis>
```

Вызов:

```
python scripts/db.py db_tables '{"pattern":"user_%"}' --connection db-parsing-dev
```

Скилл сам подставит значения из `.env` и подключится.

## Как добавить новое подключение

1. В `.env` добавить переменные с префиксом, например `DB_MY_SERVICE_*`.
2. В `connections.json` скопировать один из блоков и заменить имя
   переменных, например:

```json
"db-my-service": {
  "host":     "${DB_MY_SERVICE_HOST}",
  "port":     "${DB_MY_SERVICE_PORT}",
  "user":     "${DB_MY_SERVICE_USER}",
  "password": "${DB_MY_SERVICE_PASSWORD}",
  "database": "${DB_MY_SERVICE_NAME}",
  "db_type":  "${DB_MY_SERVICE_TYPE}"
}
```

3. Проверить: `python scripts/db.py list-connections`.
