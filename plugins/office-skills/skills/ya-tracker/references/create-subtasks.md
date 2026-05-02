# Создание подзадач и загрузка артефактов

## Создание подзадачи

```
python scripts/tracker.py issue_create '{
  "queue": "DE",
  "summary": "DE-1569/Ф1: Добавить индексы в users",
  "description": "...текст ТЗ...",
  "parent": "DE-1569",
  "tags": ["gsd", "phase-1", "bnmap-api-v2"]
}'
```

Поля:
- `queue` — очередь из `services/REPOS.md` по целевому сервису.
- `summary` — формат `{parent_key}/Ф{N}: {короткое описание}`.
- `parent` — родительская задача.
- `tags` — **обязательно** включает: `gsd`, `phase-{N}`,
  `{имя-репозитория}`. Имя репозитория — из `services/REPOS.md` /
  `<files>` в PLAN.md.

## Не заполнять

- Исполнитель (`assignee`) — назначает тимлид.
- Разработчик, спринт, оценка сложности — тимлид.
- Репозиторий-поле — тимлид.

## Обнуление исполнителя после создания

Трекер подставляет дефолтного исполнителя из настроек очереди.
Сразу после создания — **обнулить**:

```
python scripts/tracker.py issue_update '{"issue_key":"DE-1600","assignee":null}'
```

## Связи между подзадачами

```
# зависимость (dev-задача Ф2 depends on Ф1)
python scripts/tracker.py issue_create_link '{
  "issue_key": "DE-1601",
  "target_issue": "DE-1600",
  "relationship": "depends on"
}'

# параллельные задачи
python scripts/tracker.py issue_create_link '{
  "issue_key": "DE-1602",
  "target_issue": "DE-1603",
  "relationship": "relates"
}'
```

Типы связей: `relates`, `depends on`, `is dependent by`,
`is subtask for`, `is parent task for`, `duplicates`,
`is duplicated by`, `is epic of`, `has epic`.

## Загрузка артефактов

`file_path` — **абсолютный** путь (см. CLAUDE.md §9):

```
python scripts/tracker.py issue_upload_attachment '{
  "issue_key": "DE-1600",
  "file_path": "C:/projects/AI_AGENTS/o-a-v1/.planning/phases/1/PLAN.md",
  "filename": "1-1-PLAN.md"
}'
```

Типовой набор на подзадачу:
- `PROJECT.md`, `REQUIREMENTS.md` (общие, раз на все подзадачи)
- `{N}-CONTEXT.md`, `{N}-RESEARCH.md`, `{N}-{M}-PLAN.md`
- `knowledge-graph.xml` целевого сервиса (из сабмодуля)

## Форматирование описаний

- **Не использовать ID требований** (PROF-01, INFRA-01 и т.д.) в
  описаниях — они выглядят как ключи задач и путают.
- Человекочитаемые формулировки:
  - Плохо: `input для INFRA-02`
  - Хорошо: `используется в Фазе 4 для добавления индексов`
- Ссылки на другие задачи — только реальные ключи (DE-1599).

## Статус подзадачи

**Не трогать.** Все переходы по статусам подзадач — ответственность
тимлида и исполнителей. Оркестратор **не** вызывает
`issue_execute_transition` на подзадачах.

## QA-задача

Очередь QA-подзадачи = очередь родительской задачи. Отличается
тегом `testing` и связями `depends on` со всеми dev-подзадачами:

```
python scripts/tracker.py issue_create '{
  "queue": "DE",
  "summary": "DE-1569: Тестирование — индексы users",
  "description": "Тестирование фичи. Разблокируется автоматически после merge всех dev-задач.",
  "parent": "DE-1569",
  "tags": ["gsd", "testing"]
}'

# обнулить исполнителя
python scripts/tracker.py issue_update '{"issue_key":"DE-1650","assignee":null}'

# связи depends on с каждой dev-подзадачей
python scripts/tracker.py issue_create_link '{"issue_key":"DE-1650","target_issue":"DE-1600","relationship":"depends on"}'
python scripts/tracker.py issue_create_link '{"issue_key":"DE-1650","target_issue":"DE-1601","relationship":"depends on"}'
```
