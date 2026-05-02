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
Tags: gsd
Tags: gsd, phase-1                     # все из списка (AND внутри тегов — через AND)
Tags: gsd AND Tags: phase-1
Components: backend
```

## Сортировка и лимит

В самом запросе сортировки нет — используй параметры `issues_find`:
`page`, `per_page` (по умолчанию 50, макс 100).

## Типовые GSD-запросы

```
# Открытые задачи в очереди
Queue: PROJ AND Status: open

# Задачи аналитика в работе
Queue: PROJ AND Assignee: me() AND Resolution: empty()

# Подзадачи родителя
Parent: DE-1569

# QA-задачи, ожидающие разблокировки
Queue: DE AND Tags: testing AND Status: ожидает

# Задачи за последний спринт по сервису
Sprint: current() AND Tags: bnmap-api-v2
```

## Документация

Полная спецификация:
https://cloud.yandex.ru/docs/tracker/user/query-filter
