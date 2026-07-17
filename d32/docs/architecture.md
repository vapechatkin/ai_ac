# Архитектура d32

## Компоненты

- `review_pr.py` — orchestration и CLI для GitHub Actions/local dry-run.
- `github_client.py` — PR, diff, changed files, head content и upsert комментария.
- `rag.py` — обнаружение документации/кода, чанкинг и BM25 retrieval.
- `reviewer.py` — защищённый prompt Claude и оформление комментария.
- `.github/workflows/d32-ai-review.yml` — trigger и минимальные permissions.

## Trust boundary

Доверенными считаются только workflow и код `d32` из base commit. Название,
описание, автор, diff и содержимое PR head недоверенны. Они никогда не передаются
shell и не импортируются как Python-модули.

GitHub token используется только REST-клиентом. Claude получает diff и RAG-текст,
но не получает GitHub token или Anthropic key.

## Идемпотентность

Комментарий содержит скрытый маркер `<!-- d32-ai-review -->`. При следующем
событии `synchronize` бот ищет собственный комментарий с этим маркером и
обновляет его. Чужой комментарий с таким же текстом игнорируется, если его автор
не имеет тип `Bot`.

## Ограничения

- Unified diff ограничен 80 000 символов.
- Patch одного файла и head content ограничены 40 000 символов.
- Из head commit загружается не больше 30 текстовых файлов.
- Binary-файлы присутствуют в списке изменений, но не индексируются как текст.
- Это статический анализ: пайплайн не утверждает, что запускал тесты.
