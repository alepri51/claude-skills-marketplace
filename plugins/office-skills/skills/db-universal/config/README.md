# db-universal — авторизация и подключения

## Где хранятся креденшлы

**Не в скилле.** Все host/port/user/password берутся из корневого `.env`
проекта (`C:/projects/AI_AGENTS/o-a-v1/.env`). Файл `.env` в `.gitignore`
и не коммитится.

## Как устроены именованные подключения

Файл `config/connections.json` — реестр **имён** подключений.
Значения в нём — ссылки `${VAR_NAME}` на переменные из `.env`.
Сам connections.json безопасно коммитить: в нём только имена.

Пример из `.env`:

```
DB_PARSING_DEV_HOST=10.0.0.42
DB_PARSING_DEV_PORT=3306
DB_PARSING_DEV_USER=inspector
DB_PARSING_DEV_PASSWORD=secret
DB_PARSING_DEV_NAME=parsing
DB_PARSING_DEV_TYPE=mysql
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
