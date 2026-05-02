# claude-skills-marketplace

Claude Code plugin marketplace со скилами для повседневной работы:

- **db-universal** — read-only инспектор БД (MySQL, PostgreSQL, ClickHouse, Redis, MongoDB).
- **ya-tracker** — CLI-обёртка над Yandex Tracker API v2 (40+ операций).
- **ya-wiki** — CLI-обёртка над Yandex Wiki API v1 (25+ операций).

Все три скила собраны в один плагин **office-skills**.

---

## Установка

В Claude Code (CLI):

```bash
/plugin marketplace add C:\projects\claude-skills-marketplace
/plugin install office-skills@claude-skills-marketplace
```

Если репо лежит в git-хосте — используйте URL вместо локального пути:

```bash
/plugin marketplace add <git-url>
/plugin install office-skills@claude-skills-marketplace
```

После установки **перезапустите Claude Code** — `SessionStart` hook сам поставит pip-зависимости (`aiohttp`, `mcp`, DB-драйверы и т.д.) в `--user` site-packages. Повторные сессии видят маркер `.installed` и пропускают установку.

## Конфигурация токенов

1. Скопируйте `plugins/office-skills/.env.example` в корень вашего рабочего проекта как `.env`.
2. Заполните `YANDEX_TOKEN` и переменные подключений к БД.
3. Скрипты ищут `.env` от текущего каталога вверх до 8 уровней — достаточно положить файл в корень любого проекта, в котором запускается Claude Code.

## Использование

Скилы триггерятся фразами автоматически:

- `какие таблицы в parsing-dev` / `покажи схему users` → **db-universal**
- `получи задачу DE-1569` / `создай подзадачу в DE` → **ya-tracker**
- `собери страницу users/foo из вики` → **ya-wiki**

Полный список триггеров — в `SKILL.md` каждого скила.

## Подключения БД (db-universal)

Файл `plugins/office-skills/skills/db-universal/config/connections.json` описывает именованные подключения. Значения в формате `${VAR_NAME}` подставляются из `.env`. Добавляйте свои подключения по образцу.

## Структура

```
.claude-plugin/marketplace.json     ← регистрация marketplace
plugins/office-skills/
├── .claude-plugin/plugin.json      ← манифест плагина
├── hooks/                          ← SessionStart auto-install
├── skills/                         ← три SKILL.md, видимые Claude Code
├── requirements.txt
└── .env.example
```
