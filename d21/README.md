# RAG: пайплайн индексации документов

Локальный пайплайн индексации: PDF → текст → чанки (2 стратегии) → эмбеддинги
(Ollama, локально) → FAISS-индекс с метаданными.

## Корпус

3 статьи про RAG с arXiv, суммарно 77 PDF-страниц / ~325k символов (~180
страниц текстового эквивалента):

| файл | статья |
|---|---|
| `rag_lewis_2020.pdf` | Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks* (2020) |
| `rag_survey_2312.pdf` | Gao et al., *Retrieval-Augmented Generation for Large Language Models: A Survey* (2312.10997) |
| `rag_survey_2404.pdf` | Huang & Huang, *A Survey on Retrieval-Augmented Text Generation for LLMs* (2404.10981) |

## Стек

- **Извлечение текста**: PyMuPDF (`fitz`) — текст по страницам + встроенное
  оглавление PDF (TOC/bookmarks) для определения структуры разделов.
- **Эмбеддинги**: локальная модель `nomic-embed-text` (768-мерная) через
  Ollama, без внешних API.
- **Индекс**: FAISS (`IndexFlatIP` + L2-нормализация = косинусное сходство).
- **Метаданные**: JSON рядом с индексом (`source`, `title`, `section`,
  `page`, `chunk_id`, `strategy`).

## Пайплайн

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
brew install ollama && brew services start ollama && ollama pull nomic-embed-text

python extract.py        # PDF -> data/parsed/*.json (текст + разделы по TOC)
python chunking.py       # -> data/chunks/{fixed,structure}.json
python embed.py          # -> data/embeddings/{fixed,structure}.npy
python build_index.py    # -> data/index/{fixed,structure}.faiss + *_meta.json
python compare.py        # сравнение стратегий, отчёт в data/comparison_report.md
```

## Две стратегии chunking

1. **fixed** — окно 1000 символов, перекрытие 150, без учёта структуры
   документа. Режет текст механически, может разорвать раздел/предложение
   пополам.
2. **structure** — границы чанков = границы разделов (заголовки из
   встроенного TOC PDF). Разделы длиннее 1500 символов дополнительно режутся
   тем же fixed-сплиттером, но чанк никогда не пересекает границу раздела.
   Каждый чанк несёт осмысленный `section` (например, `"2.1 Models"`,
   `"Naive RAG"`).

## Результаты сравнения

| | fixed | structure |
|---|---|---|
| чанков всего | 383 | 321 |
| средний размер | 997 симв. (σ=42) | 1242 симв. (σ=427) |
| min/max | 227 / 1000 | 102 / 1500 |
| `section` в метаданных | всегда `null` | осмысленное название раздела |

На 5 тестовых запросах (см. `data/comparison_report.md`) top-1 similarity
score у **structure** выше в 4 из 5 случаев (например, 0.786 vs 0.731 для
вопроса про RAG-Sequence/RAG-Token, 0.897 vs 0.818 про метрики оценки RAG).
Разница особенно заметна там, где релевантный фрагмент — это конкретный
подраздел (`"2.1 Models"`, `"Required Abilities"`): fixed-чанк в таком месте
часто захватывает конец предыдущего раздела и начало следующего, размывая
эмбеддинг, а structure-чанк остаётся семантически цельным.

**Вывод**: structure-based chunking даёт более точный retrieval и
единственная стратегия из двух, где метаданные `section` реально полезны
(можно фильтровать/группировать результаты по разделу). Fixed-size проще в
реализации и не зависит от наличия структуры в документе (работает даже без
TOC/заголовков), но качество поиска в среднем хуже. На практике имеет смысл
комбинировать: structure как основной сплиттер, fixed — как fallback для
документов без чёткой структуры.

## Структура проекта

```
data/
  raw/          — исходные PDF
  parsed/       — текст + разделы по каждому документу (extract.py)
  chunks/       — чанки обеих стратегий с метаданными (chunking.py)
  embeddings/   — .npy векторы эмбеддингов (embed.py)
  index/        — FAISS-индексы + метаданные чанков (build_index.py)
  comparison_report.md — отчёт сравнения (compare.py)
```
