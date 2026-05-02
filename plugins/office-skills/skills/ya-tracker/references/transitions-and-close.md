# Транзиции статусов и закрытие задач

> Скилл предоставляет операции `issue_execute_transition`,
> `issue_get_transitions`, `issue_close`. Здесь — только синтаксис вызовов.
> Политику переходов задаёт вызывающая сторона.

## Закрытие задачи

```
python scripts/tracker.py issue_close '{
  "issue_key": "DE-1569",
  "resolution_id": "fixed",
  "comment": "Все подзадачи закрыты, фича принята."
}'
```

Доступные `resolution_id` зависят от типа задачи. Посмотреть:

```
python scripts/tracker.py get_resolutions '{}'
```

Типовые: `fixed`, `wontFix`, `duplicate`, `cantReproduce`.

## Если нужен явный transition

Сначала узнать доступные переходы:

```
python scripts/tracker.py issue_get_transitions '{"issue_key":"DE-1569"}'
```

Ответ:
```json
[
  {"id": "start_progress", "display": "Начать выполнение", "to": "inProgress"},
  {"id": "resolve", "display": "Завершить", "to": "resolved"}
]
```

Выполнить:

```
python scripts/tracker.py issue_execute_transition '{
  "issue_key": "DE-1569",
  "transition_id": "start_progress",
  "comment": "Беру в анализ"
}'
```

## Поля при транзиции

Некоторые транзиции требуют `resolution` или других полей:

```
python scripts/tracker.py issue_execute_transition '{
  "issue_key": "DE-1569",
  "transition_id": "resolve",
  "fields": {"resolution": "fixed"}
}'
```

## Приёмка подзадач (verify-work)

Для каждой подзадачи после успешного ревью:

```
python scripts/tracker.py issue_close '{
  "issue_key": "DE-1600",
  "resolution_id": "fixed",
  "comment": "Принято. PLAN.md выполнен."
}'
```

Если расхождение — оставить комментарий с описанием и **не** закрывать:

```
python scripts/tracker.py issue_add_comment '{
  "issue_key": "DE-1600",
  "text": "Не приняли. Расхождения:\n- Индекс idx_users_email не создан.\n- MR ...changes показывает ..."
}'
```
