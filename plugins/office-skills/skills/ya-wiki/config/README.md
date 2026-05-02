# ya-wiki — авторизация

## Переменные в корневом `.env`

`.env` лежит в корне проекта и должен быть в `.gitignore`.
Скилл читает его автоматически при запуске.

```
# === Yandex (общие для tracker + wiki) ===
YANDEX_TOKEN=y0_AgAAAA...                  # OAuth-токен (обязателен)
YANDEX_CLOUD_ORG_ID=bpf...                 # для Yandex Cloud Organization
# или для Yandex 360:
# YANDEX_ORG_ID=1234567

# === Wiki (опции) ===
WIKI_BASE_URL=https://api.wiki.yandex.net  # по умолчанию
WIKI_DOWNLOAD_DIR=downloads                # куда класть скачанные вложения
```

Нужен ровно один из `YANDEX_CLOUD_ORG_ID` или `YANDEX_ORG_ID`.
`YANDEX_CLOUD_ORG_ID` имеет приоритет, если заполнены оба.

Один и тот же `YANDEX_TOKEN` используется и для `ya-tracker`, и для `ya-wiki`,
если при создании OAuth-приложения выбраны оба scope (`tracker:write` +
`wiki:write`). Org-id у обоих сервисов один — берётся в Tracker:
**Администрирование → Организации → Идентификатор**
(<https://tracker.yandex.ru/admin/orgs>).

## Как получить токен

1. Открыть <https://oauth.yandex.ru/>
2. Создать приложение → **Для доступа к API или отладки** → указать название и email.
3. Добавить разрешения:
   - **Яндекс Вики: чтение и запись данных** (`wiki:write`) — для полного доступа.
   - либо **Яндекс Вики: только чтение** (`wiki:read`) — если планируешь только
     read-операции.
   - Если параллельно нужен Tracker — добавь **Яндекс.Трекер: чтение и запись**
     (`tracker:write`) в **то же** приложение.
4. Скопировать **ClientID** из карточки приложения.
5. Перейти по ссылке: `https://oauth.yandex.ru/authorize?response_type=token&client_id=<ClientID>`
6. Скопировать токен в `.env` как `YANDEX_TOKEN=y0_...`.

## Проверка

```
python scripts/wiki.py users_get_current '{}'
```

Должен вернуть JSON с `username`, `uid`, `dir_id` текущего пользователя.

Если возвращается `Error 401` — токен невалидный или у него нет scope `wiki:read`.
Если `Error 403` — токен валидный, но нет доступа к организации
(проверь `YANDEX_ORG_ID` / `YANDEX_CLOUD_ORG_ID`).
Если `TOKEN=MISSING` в stderr при запуске — `.env` не найден или
переменная пустая.

## Безопасность

- **Не коммитить `.env`** — он в `.gitignore`.
- **Не выводить токен в чат** — даже в сокращённом виде.
- **Не писать токен в скрипты/репорт/коммит.**

Токен даёт полный доступ к Вики и Трекеру организации (если выданы оба scope).
Если случайно попал в git-историю — **отозвать** через https://oauth.yandex.ru/
и создать новый.
