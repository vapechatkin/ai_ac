"""
Извлечение текста из PDF с сохранением структуры документа
(заголовки/разделы), чтобы потом строить structure-based chunking.

Заголовки берём из встроенного оглавления PDF (bookmarks/TOC) —
это надёжнее, чем эвристика по размеру шрифта на многоколоночных
академических статьях.

Для каждого PDF из data/raw/ сохраняем в data/parsed/<doc_id>.json:
  - plain_text: весь текст документа (для fixed-size chunking)
  - sections: список {level, title, page, text} по границам TOC
              (для structure-based chunking)
"""

import json
import os
import re

import fitz  # PyMuPDF

RAW_DIR = os.path.join(os.path.dirname(__file__), "data", "raw")
PARSED_DIR = os.path.join(os.path.dirname(__file__), "data", "parsed")


def doc_title(pdf: fitz.Document, fallback: str) -> str:
    meta_title = (pdf.metadata or {}).get("title") or ""
    if meta_title and len(meta_title) > 3:
        return meta_title.strip()
    return fallback


def find_heading(text: str, title: str, start_from: int = 0):
    """Ищем заголовок в тексте, допуская перенос строки/пробелы между словами
    (PDF часто разбивает "2.1 Models" на "2.1\\nModels")."""
    pattern = r"\s+".join(re.escape(w) for w in title.split())
    m = re.search(pattern, text[start_from:])
    if not m:
        return None
    return start_from + m.start(), start_from + m.end()


def build_sections(toc: list, page_texts: dict, n_pages: int) -> list:
    """Режем текст на секции по границам TOC-записей (страницы)."""
    sections = []
    for i, (level, title, page) in enumerate(toc):
        start_page = page
        end_page = toc[i + 1][2] if i + 1 < len(toc) else n_pages

        parts = [page_texts.get(p, "") for p in range(start_page, min(end_page, n_pages) + 1)]
        text = "\n".join(parts)

        start_match = find_heading(text, title)
        if start_match:
            text = text[start_match[1]:]

        if i + 1 < len(toc):
            next_title = toc[i + 1][1]
            end_match = find_heading(text, next_title)
            if end_match and end_match[0] > 30:  # не обрезаем при слишком раннем совпадении
                text = text[:end_match[0]]

        text = text.strip()
        if text:
            sections.append({"level": level, "title": title, "page": start_page, "text": text})
    return sections


def extract_pdf(path: str) -> dict:
    pdf = fitz.open(path)
    doc_id = os.path.splitext(os.path.basename(path))[0]
    title = doc_title(pdf, fallback=doc_id)
    n_pages = pdf.page_count

    page_texts = {}
    plain_lines = []
    for page_num, page in enumerate(pdf, start=1):
        text = page.get_text("text").strip()
        page_texts[page_num] = text
        if text:
            plain_lines.append(text)

    toc = pdf.get_toc()  # [[level, title, page], ...]
    sections = build_sections(toc, page_texts, n_pages)

    pdf.close()
    return {
        "doc_id": doc_id,
        "title": title,
        "n_pages": n_pages,
        "n_sections": len(sections),
        "sections": sections,
        "plain_text": "\n".join(plain_lines),
    }


def main():
    os.makedirs(PARSED_DIR, exist_ok=True)
    pdf_files = sorted(f for f in os.listdir(RAW_DIR) if f.lower().endswith(".pdf"))
    if not pdf_files:
        print(f"Нет PDF в {RAW_DIR}")
        return

    total_chars = 0
    for fname in pdf_files:
        path = os.path.join(RAW_DIR, fname)
        result = extract_pdf(path)
        n_chars = len(result["plain_text"])
        total_chars += n_chars

        out_json = os.path.join(PARSED_DIR, result["doc_id"] + ".json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(
            f"{fname}: {n_chars} символов, {result['n_pages']} страниц, "
            f"{result['n_sections']} разделов -> {out_json}"
        )

    print(f"\nВсего символов: {total_chars} (~{total_chars // 1800} страниц эквивалент)")


if __name__ == "__main__":
    main()
