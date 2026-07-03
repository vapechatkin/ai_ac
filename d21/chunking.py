"""
Две стратегии chunking поверх извлечённых документов (data/parsed/*.json):

1. fixed   — разбиение по фиксированному размеру символов с перекрытием,
             без учёта структуры документа.
2. structure — разбиение по разделам (заголовки из TOC PDF); если раздел
             больше max_size, дополнительно режем его тем же fixed-splitter'ом,
             но не пересекаем границы разделов.

Каждый чанк получает метаданные: source, title, section, chunk_id, page.
Результат сохраняется в data/chunks/fixed.json и data/chunks/structure.json.
"""

import json
import os

PARSED_DIR = os.path.join(os.path.dirname(__file__), "data", "parsed")
CHUNKS_DIR = os.path.join(os.path.dirname(__file__), "data", "chunks")

FIXED_SIZE = 1000       # символов на чанк (~200-250 токенов)
FIXED_OVERLAP = 150      # символов перекрытия между соседними чанками


def split_fixed(text: str, size: int = FIXED_SIZE, overlap: int = FIXED_OVERLAP) -> list:
    """Режем текст на окна фиксированного размера с перекрытием."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    step = max(size - overlap, 1)
    while start < n:
        end = min(start + size, n)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end == n:
            break
        start += step
    return chunks


def chunk_fixed(doc: dict) -> list:
    """Стратегия 1: фиксированный размер по всему тексту документа, без учёта структуры."""
    chunks = []
    pieces = split_fixed(doc["plain_text"])
    for i, piece in enumerate(pieces):
        chunks.append({
            "chunk_id": f"{doc['doc_id']}__fixed__{i:04d}",
            "source": doc["doc_id"],
            "title": doc["title"],
            "section": None,
            "page": None,
            "strategy": "fixed",
            "text": piece,
            "char_count": len(piece),
        })
    return chunks


def chunk_structure(doc: dict, max_size: int = 1500) -> list:
    """Стратегия 2: разбиение по разделам (заголовкам), длинные разделы режем доп. окнами,
    но не пересекаем границы разделов."""
    chunks = []
    sections = doc.get("sections") or []
    if not sections:
        # нет TOC/разделов в документе — используем весь текст как один "раздел"
        sections = [{"level": 1, "title": doc["title"], "page": None, "text": doc["plain_text"]}]

    for sec_idx, sec in enumerate(sections):
        text = sec["text"].strip()
        if not text:
            continue
        if len(text) <= max_size:
            pieces = [text]
        else:
            pieces = split_fixed(text, size=max_size, overlap=FIXED_OVERLAP)
        for i, piece in enumerate(pieces):
            chunks.append({
                "chunk_id": f"{doc['doc_id']}__struct__{sec_idx:04d}_{i:02d}",
                "source": doc["doc_id"],
                "title": doc["title"],
                "section": sec["title"],
                "page": sec.get("page"),
                "strategy": "structure",
                "text": piece,
                "char_count": len(piece),
            })
    return chunks


def main():
    os.makedirs(CHUNKS_DIR, exist_ok=True)
    doc_files = sorted(f for f in os.listdir(PARSED_DIR) if f.endswith(".json"))
    if not doc_files:
        print(f"Нет распарсенных документов в {PARSED_DIR}, запусти extract.py")
        return

    fixed_chunks, structure_chunks = [], []
    for fname in doc_files:
        with open(os.path.join(PARSED_DIR, fname), encoding="utf-8") as f:
            doc = json.load(f)
        fixed_chunks.extend(chunk_fixed(doc))
        structure_chunks.extend(chunk_structure(doc))

    with open(os.path.join(CHUNKS_DIR, "fixed.json"), "w", encoding="utf-8") as f:
        json.dump(fixed_chunks, f, ensure_ascii=False, indent=2)
    with open(os.path.join(CHUNKS_DIR, "structure.json"), "w", encoding="utf-8") as f:
        json.dump(structure_chunks, f, ensure_ascii=False, indent=2)

    def stats(chunks, name):
        sizes = [c["char_count"] for c in chunks]
        avg = sum(sizes) / len(sizes) if sizes else 0
        print(f"{name}: {len(chunks)} чанков, средний размер {avg:.0f} симв., "
              f"min={min(sizes) if sizes else 0}, max={max(sizes) if sizes else 0}")

    stats(fixed_chunks, "fixed")
    stats(structure_chunks, "structure")


if __name__ == "__main__":
    main()
