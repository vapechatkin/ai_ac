# d33 — AI-ассистент службы поддержки

Мини-сервис отвечает на вопросы о продукте «Капитолия», ищет факты в локальной
базе знаний (RAG) и учитывает данные конкретного пользователя или тикета из
JSON CRM. Доступ к CRM происходит через отдельный локальный MCP-сервер.

## Что реализовано

- `POST /support` — вопрос без контекста, с `user_id` или с `ticket_id`;
- RAG по FAQ, документации продукта и инструкциям диагностики;
- read-only MCP-инструменты для пользователей и тикетов;
- Claude Haiku как недорогая модель по умолчанию;
- долгоживущая MCP-сессия и индекс RAG, создаваемый один раз при старте;
- ссылки на использованные фрагменты базы знаний в ответе;
- синтетические данные CRM без реальных персональных данных.

## Архитектура

```text
POST /support
      |
      v
 FastAPI -> CRM MCP client --stdio--> JSON CRM MCP server -> data/crm.json
      |
      +-> question + ticket/user facts -> BM25 RAG -> knowledge/*.md
      |
      +-> CRM context + retrieved docs -> Claude Haiku -> support response
```

Подробности находятся в [docs/architecture.md](docs/architecture.md).

## Быстрый запуск

Требуется Python 3.11+ и ключ Anthropic API.

```bash
cd d33
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Запишите ключ только в локальный `d33/.env`:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-haiku-4-5
```

Файл `.env` исключён из Git. Проверить это можно командой
`git check-ignore d33/.env` из корня репозитория.

Запуск сервиса:

```bash
cd d33
source .venv/bin/activate
uvicorn server:app --reload --port 8033
```

Документация API будет доступна по адресу <http://127.0.0.1:8033/docs>.

## Проверка

Обращение с контекстом тикета:

```bash
curl -s http://127.0.0.1:8033/support \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "Почему не работает авторизация?",
    "ticket_id": "TCK-101"
  }'
```

Из тикета сервис узнает, что это Android после переустановки, код ошибки —
`unauthorized`, а аккаунт активен. Поэтому ответ будет конкретнее общего FAQ:
повторить гостевой вход, не использовать старый токен и эскалировать потерю
важной партии для ручной проверки.

Можно обратиться только с контекстом пользователя:

```bash
curl -s http://127.0.0.1:8033/support \
  -H 'Content-Type: application/json' \
  -d '{"question":"Как войти в комнату?","user_id":"usr_1002"}'
```

Или задать общий вопрос без CRM-контекста:

```bash
curl -s http://127.0.0.1:8033/support \
  -H 'Content-Type: application/json' \
  -d '{"question":"Поддерживается ли восстановление покупок?"}'
```

Демонстрационные тикеты: `TCK-101`, `TCK-102`, `TCK-103`.

## MCP CRM

`crm_mcp_server.py` запускается сервисом автоматически через stdio. Он отдаёт
четыре read-only инструмента:

- `get_user(user_id)`;
- `get_ticket(ticket_id)`;
- `get_ticket_context(ticket_id)`;
- `list_user_tickets(user_id, status)`.

Источник данных задаётся переменной `D33_CRM_FILE`; по умолчанию используется
`data/crm.json`. Такой адаптер можно позднее заменить настоящей CRM, не меняя
основную последовательность обработки запроса.

## RAG

При старте Markdown-файлы из `knowledge/` разбиваются на фрагменты и индексируются
локальным BM25-поиском. В запрос к поиску входят вопрос, описание и код ошибки
тикета, платформа, версия приложения и статус аккаунта. Внешняя vector database
для учебного примера не требуется, а повторное «обучение» при каждом вопросе не
происходит.

## Тесты

```bash
cd d33
source .venv/bin/activate
pytest -q
```

Тесты проверяют JSON CRM, настоящий MCP transport, RAG, объединение контекстов и
HTTP API. Они используют fake LLM и не расходуют Anthropic API credits.

## Ограничения демо

- CRM содержит только синтетические записи.
- HTTP API пока не имеет аутентификации и предназначен для локального запуска.
- Для production нужны контроль доступа, маскирование PII, аудит, rate limiting
  и защищённое хранилище секретов.
