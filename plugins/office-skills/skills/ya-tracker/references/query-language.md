# Tracker Query Language — шпаргалка

Используется в `issues_find` и `issues_count`.

## Базовые фильтры

```
Queue: DE
Queue: DE AND Status: open
Queue: DE AND Status: open AND Assignee: me()
Queue: DE AND Status: !closed         # NOT через !
Queue: DE, BACK                       # несколько значений — список через запятую
```

## Даты

```
Updated: today()
Updated: yesterday()
Updated: today() - 7d                  # за последнюю неделю
Created: "2026-01-01" .. "2026-04-01"  # диапазон
Resolved: empty()                      # поле пустое
```

## Связи

```
Parent: DE-1569                        # подзадачи конкретного родителя
Links: "depends on" DE-1569            # всё, что зависит от DE-1569
```

## Пользователи

```
Assignee: me()                         # на мне
Assignee: empty()                      # без исполнителя
Author: login_user                     # автор
Followers: me()                        # я в наблюдателях
```

## Теги и компоненты

```
Tags: my-tag
Tags: tag-a, tag-b                     # любой из списка
Tags: tag-a AND Tags: tag-b            # оба
Components: backend
```

## Сортировка и лимит

В самом запросе сортировки нет — используй параметры `issues_find`:
`page`, `per_page` (по умолчанию 50, макс 100).

## Типовые запросы

```
# Открытые задачи в очереди
Queue: PROJ AND Status: open

# Активные задачи текущего пользователя
Queue: PROJ AND Assignee: me() AND Resolution: empty()

# Подзадачи родителя
Parent: DE-1569

# Задачи с тегом, в указанном статусе
Queue: DE AND Tags: testing AND Status: ожидает

# Задачи текущего спринта по тегу
Sprint: current() AND Tags: my-tag
```

## Документация

Полная спецификация:
https://cloud.yandex.ru/docs/tracker/user/query-filter
