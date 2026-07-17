# d32 — автоматическое AI-ревью pull request

GitHub Actions-пайплайн получает новый PR через GitHub REST API, строит RAG по
документации и исходному коду проекта, отправляет diff и релевантный контекст в
Claude и публикует Markdown-ревью в комментарии к PR.

## Результат ревью

Комментарий содержит обязательные разделы:

- потенциальные баги;
- архитектурные проблемы;
- рекомендации;
- краткое резюме изменений.

Каждое замечание должно включать приоритет `P0`–`P3`, файл, строку, объяснение
риска и предлагаемое исправление. Повторный запуск обновляет предыдущий
AI-комментарий вместо создания нового.

## Как работает пайплайн

```text
pull_request_target
        │
        ├── checkout только доверенного base commit
        ├── GitHub API: PR + changed files + unified diff
        ├── GitHub API: текст изменённых файлов из head commit
        │
        ├── BM25 RAG
        │     ├── README и docs
        │     ├── OpenAPI/схемы
        │     ├── исходный код base
        │     └── изменённый код head
        │
        ├── Claude Haiku: diff + RAG-контекст
        └── create/update PR comment
```

Вся логика ассистента находится в `d32`. Файл
`.github/workflows/d32-ai-review.yml` — обязательный GitHub-trigger: workflow в
другом каталоге GitHub Actions не обнаружит.

## Настройка GitHub

1. Откройте репозиторий на GitHub.
2. Перейдите в `Settings → Secrets and variables → Actions`.
3. Создайте repository secret с именем `ANTHROPIC_API_KEY`.
4. Убедитесь, что `d32` и workflow находятся в default branch.
5. Создайте PR или добавьте в существующий PR новый commit.

Workflow запускается на событиях `opened`, `synchronize`, `reopened` и
`ready_for_review`. Draft PR пропускается до перевода в ready-for-review.

## Безопасность

Используется `pull_request_target`, потому что пайплайну нужны secret Claude и
право оставить комментарий. Для этого события особенно важно не выполнять код
из PR:

- checkout выполняется строго по `base.sha`;
- `persist-credentials` отключён;
- PR head не запускается и его зависимости не устанавливаются;
- diff и изменённые файлы читаются через API как недоверенный текст;
- системный промпт запрещает выполнять инструкции из diff или документации;
- разрешения ограничены `contents: read` и `pull-requests: write`.

`ANTHROPIC_API_KEY`, локальный `.env`, приватные ключи и виртуальное окружение
исключены из Git. В репозиторий попадает только `.env.example` с placeholder.

## RAG

Индекс использует BM25 с токенами слов, идентификаторов и символьных триграмм.
Он индексирует два типа контекста и балансирует результаты:

- до четырёх фрагментов документации;
- до шести фрагментов исходного кода.

Поддерживаются распространённые языки: Python, JavaScript/TypeScript, Dart, Go,
Rust, Java/Kotlin, Swift, C/C++, C#, Ruby, PHP, Scala, Shell и SQL. Также
индексируются Markdown, HTML, JSON, YAML, TOML, GraphQL, Proto и API-схемы.
Build-каталоги, зависимости, lock-файлы, generated-код и файлы больше 600 КБ
пропускаются.

## Модель

По умолчанию используется экономичная модель:

```env
CLAUDE_MODEL=claude-haiku-4-5
```

Модель можно поменять в workflow или repository variable без изменения логики.

## Локальная проверка

```bash
cd /Users/viktor/ai_ac/d32
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Заполните локальный `.env`, затем запустите без публикации комментария:

```bash
python review_pr.py \
  --repo vapechatkin/ai_ac \
  --pr 123 \
  --workspace /Users/viktor/ai_ac \
  --dry-run
```

Для локального чтения PR токену GitHub достаточно доступа на чтение
репозитория. Без `--dry-run` также потребуется право писать PR-комментарии.

## Тесты

```bash
pytest -q
```

Тесты используют mock GitHub API и не расходуют Claude API.
