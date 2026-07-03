"""
Прогоняет 10 контрольных вопросов (questions.json, те же, что в d22) во
всех режимах rag2.MODES и считает те же эвристические метрики, что в d22:

- keyword_coverage: доля ожидаемых ключевых слов/фактов в ответе
- source_hit / section_hit: попал ли хоть один из kept-чанков в ожидаемый
  документ/раздел
- n_retrieved / n_kept: топ-K до и после фильтрации

Результат сохраняется в results.json.
"""

import json
import os
import time

import rag2

BASE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_PATH = os.path.join(BASE, "questions.json")
RESULTS_PATH = os.path.join(BASE, "results.json")

MODES = ["no_rag", "baseline", "threshold", "llm_rerank", "rewrite_filter"]


def keyword_coverage(text: str, keywords: list) -> float:
    if not keywords:
        return 1.0
    text_low = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_low)
    return hits / len(keywords)


def source_hit(kept: list, expected_sources: list) -> bool:
    return any(c["source"] in expected_sources for c in kept)


def section_hit(kept: list, expected_sections: list) -> bool:
    exp_low = [s.lower() for s in expected_sections]
    for c in kept:
        sec = (c["section"] or "").lower()
        if sec and any(e in sec or sec in e for e in exp_low):
            return True
    return False


def main():
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        questions = json.load(f)

    results = []
    for q in questions:
        print(f"[{q['id']}/{len(questions)}] {q['question']}")
        entry = {
            "id": q["id"], "question": q["question"],
            "expected_keywords": q["expected_keywords"],
            "expected_sources": q["expected_sources"],
            "expected_sections": q["expected_sections"],
            "modes": {},
        }

        for mode in MODES:
            t0 = time.time()
            r = rag2.answer(q["question"], mode)
            latency = round(time.time() - t0, 2)

            cov = keyword_coverage(r["text"], q["expected_keywords"])
            entry_mode = {
                "text": r["text"],
                "keyword_coverage": cov,
                "n_retrieved": len(r["retrieved"]),
                "n_kept": len(r["kept"]),
                "input_tokens": r["input_tokens"],
                "output_tokens": r["output_tokens"],
                "latency_sec": latency,
            }
            if mode != "no_rag":
                entry_mode["source_hit"] = source_hit(r["kept"], q["expected_sources"])
                entry_mode["section_hit"] = section_hit(r["kept"], q["expected_sections"])
            if "rewritten_query" in r:
                entry_mode["rewritten_query"] = r["rewritten_query"]

            entry["modes"][mode] = entry_mode
            extra = f" src={entry_mode.get('source_hit')}" if mode != "no_rag" else ""
            print(f"  {mode:16s} cov={cov:.2f} kept={entry_mode['n_kept']}/{entry_mode['n_retrieved']}{extra}")

        results.append(entry)

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    n = len(results)
    for mode in MODES:
        avg_cov = sum(r["modes"][mode]["keyword_coverage"] for r in results) / n
        line = f"{mode:16s} avg keyword_coverage={avg_cov:.2f}"
        if mode != "no_rag":
            src_rate = sum(r["modes"][mode]["source_hit"] for r in results) / n
            sec_rate = sum(r["modes"][mode]["section_hit"] for r in results) / n
            avg_kept = sum(r["modes"][mode]["n_kept"] for r in results) / n
            line += f" | source_hit={src_rate:.2f} | section_hit={sec_rate:.2f} | avg_kept={avg_kept:.1f}"
        print(line)

    print(f"\nРезультаты сохранены в {RESULTS_PATH}")


if __name__ == "__main__":
    main()
