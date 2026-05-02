# Сбор контекста задачи (глубина 2)

Стандартный workflow оркестратора: аналитик назвал задачу, нужно
собрать полный контекст до планирования.

## Уровни задач

- **Уровень 0** — задача, которую выбрал аналитик.
- **Уровень 1** — все связанные задачи уровня 0 (parent, related,
  duplicates, sub-tasks, blocks и т.д.).
- **Уровень 2** — все связанные задачи задач уровня 1.
- Глубже **не идём** — сбор взорвётся.

## Уровни 0 и 1 — полный набор вызовов

```
python scripts/tracker.py issue_get            '{"issue_key":"DE-1569"}'
python scripts/tracker.py issue_get_links      '{"issue_key":"DE-1569"}'
python scripts/tracker.py issue_get_comments   '{"issue_key":"DE-1569"}'
python scripts/tracker.py issue_get_attachments '{"issue_key":"DE-1569"}'
```

Для каждого текстового вложения (pdf, docx, md) — скачать:

```
python scripts/tracker.py issue_download_attachment \
  '{"issue_key":"DE-1569","attachment_id":12345,"filename":"TRD.pdf"}'
```

## Уровень 2 — только базовые поля

```
python scripts/tracker.py issue_get '{"issue_key":"DE-1742","include_description":false}'
```

Комментарии, вложения, links на уровне 2 **не** тянем — достаточно
понимать, что такая задача есть и о чём она.

## Сканирование URL в описании и комментариях

Пройтись по тексту и разделить ссылки по типу:

- **Трекер** (`tracker.yandex.ru/XXX-123`) → **не** `WebFetch`.
  Добавить задачу в очередь следующего уровня (если сейчас на 0 →
  уровень 1 → полный набор; если сейчас на 1 → уровень 2 → только
  `issue_get`).
- **GitLab** (MR, issues, blob/raw) → `curl -H "PRIVATE-TOKEN:
  $GITLAB_PAT"` (см. CLAUDE.md §5.3). **Не** `WebFetch` — у него нет
  авторизации, приватные проекты вернут 401.
- **Внешние доки** (Confluence, Wiki, Google Docs, Figma, Swagger) →
  `WebFetch(url)` + краткое резюме в сводку.

## Итог

После полного обхода — сводка аналитику:

- Что в описании задачи
- Какие вложения скачаны
- Какие связанные задачи найдены (их summary — по `issue_get`)
- Какие внешние документы изучены (URL + краткое резюме)
- Какие сервисы предположительно затронуты (из REPOS.md)
- Какие сервисы упомянуты, но не подключены как сабмодули

## Важно: ветка задачи — до скачивания

Все скачанные вложения (`issue_download_attachment`) идут в
`<DOWNLOAD_DIR>/<issue_key>/<filename>` (относительно CWD). Ветка
задачи должна быть создана **до** первого скачивания, чтобы
вложения попали в ветку, а не в `main`. См. CLAUDE.md §6.1.
