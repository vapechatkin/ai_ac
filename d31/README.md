# d31 — ассистент разработчика с RAG, MCP и Claude

CLI-ассистент подключается к Git-репозиторию через локальный MCP-сервер,
индексирует проектную документацию и отвечает на `/help` с помощью Claude API.

## Возможности

- принимает только Git URL, а не локальный путь;
- клонирует и обновляет репозиторий через MCP over stdio;
- получает текущую ветку и commit отдельными MCP-инструментами;
- индексирует `README`, `docs`, OpenAPI/Swagger/AsyncAPI и файлы схем;
- сохраняет репозиторий и RAG-индекс между запусками;
- автоматически перестраивает индекс при изменении commit;
- при недоступной сети использует ранее сохранённый кэш;
- отправляет Claude только найденные фрагменты, а не весь репозиторий;
- отвечает только по команде `/help "вопрос"`.

## Архитектура

```text
Git URL
  │
  ▼
assistant.py ──MCP stdio──> mcp_server.py
  │                           ├── connect_repository
  │                           ├── git_branch
  │                           ├── git_commit
  │                           └── list_files
  │
  ├── repository cache
  ├── persistent BM25 RAG index
  └── relevant chunks + Git context ──> Claude API ──> answer
```

RAG использует лексический BM25-индекс с дополнительными символьными токенами.
Такой индекс не требует отдельного embedding API, хорошо ищет русские формы и
идентификаторы кода и работает на Python 3.14 без PyTorch. Это именно retrieval-
этап: Claude получает только несколько наиболее релевантных фрагментов.

## Установка

```bash
cd /Users/viktor/ai_ac/d31
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Откройте `.env` и добавьте ключ:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key
CLAUDE_MODEL=claude-haiku-4-5
```

`.env` и весь каталог `data` исключены из Git.

## Первый запуск

```bash
source .venv/bin/activate
python assistant.py https://github.com/vapechatkin/capitoly.git
```

Ассистент через MCP клонирует проект, получает ветку и commit, строит индекс и
переходит в CLI:

```text
Проект подключён: https://github.com/vapechatkin/capitoly.git
Ветка: main · commit: c369f9b...
RAG построен: 8 файлов, 42 фрагмента
Введите /help "вопрос по проекту" или /exit.
> /help "Как устроено взаимодействие клиента и сервера?"
```

Кавычки необязательны:

```text
> /help Как запустить сервер локально?
```

Доступны только две CLI-команды:

- `/help <вопрос>` — ответ по проектной документации;
- `/exit` — завершение работы.

## Повторный запуск

```bash
python assistant.py
```

Последний Git URL хранится в `data/state.json`. При запуске MCP проверяет remote:

- тот же commit — готовый индекс загружается с диска;
- новый commit — cached clone обновляется, индекс перестраивается;
- remote временно недоступен — используется последняя сохранённая версия;
- другой URL в аргументе — создаётся независимый кэш нового проекта.

Кэш имеет структуру:

```text
data/
├── state.json
└── projects/<url-hash>/
    ├── repository/
    └── rag/
        ├── index.json
        └── metadata.json
```

## Что индексируется

- файлы с именем `README*`;
- поддерживаемые текстовые файлы внутри `docs`, `doc`, `documentation`;
- файлы, в имени которых есть `openapi`, `swagger`, `asyncapi`, `schema`, `api`.

Поддерживаются Markdown, MDX, RST, TXT, HTML, YAML и JSON. Пропускаются `.git`,
`build`, `dist`, `.dart_tool`, `node_modules`, `vendor`, скрытые каталоги и файлы
больше 1 МБ.

## Проверка

```bash
pytest -q
```

Тесты не используют GitHub и Claude API: они проверяют определение проекта,
поиск документации, чанкинг, ранжирование, сохранение индекса и CLI-парсер.

## Соответствие заданию

- README и `docs` участвуют в RAG;
- API-описания и схемы также попадают в индекс;
- Git-репозиторий подключается MCP-клиентом к MCP-серверу;
- текущая ветка получается инструментом `git_branch`;
- `/help` использует RAG-контекст, Git branch/commit и Claude;
- состояние проекта сохраняется между запусками.
