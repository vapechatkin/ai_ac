"""
Прогоняет 10 контрольных вопросов (questions.json) в двух режимах —
без RAG и с RAG — и считает простые эвристические метрики качества:

- keyword_coverage: доля ожидаемых ключевых слов/фактов, найденных в ответе
  (регистронезависимый substring-поиск)
- source_hit / section_hit (только для RAG): попал ли хоть один из
  retrieved-чанков в ожидаемый источник/раздел

Результат сохраняется в results.json для последующей визуализации.
"""

import json
import os
import time

import rag

BASE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_PATH = os.path.join(BASE, "questions.json")
RESULTS_PATH = os.path.join(BASE, "results.json")


def keyword_coverage(text: str, keywords: list) -> float:
    if not keywords:
        return 1.0
    text_low = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_low)
    return hits / len(keywords)


def source_hit(retrieved: list, expected_sources: list) -> bool:
    return any(r["source"] in expected_sources for r in retrieved)


def section_hit(retrieved: list, expected_sections: list) -> bool:
    exp_low = [s.lower() for s in expected_sections]
    for r in retrieved:
        sec = (r["section"] or "").lower()
        if any(e in sec or sec in e for e in exp_low if sec):
            return True
    return False


def main():
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        questions = json.load(f)

    results = []
    for q in questions:
        print(f"[{q['id']}/{len(questions)}] {q['question']}")

        t0 = time.time()
        no_rag = rag.answer(q["question"], "no_rag")
        t_no_rag = time.time() - t0

        t0 = time.time()
        rag_res = rag.answer(q["question"], "rag")
        t_rag = time.time() - t0

        no_rag_cov = keyword_coverage(no_rag["text"], q["expected_keywords"])
        rag_cov = keyword_coverage(rag_res["text"], q["expected_keywords"])
        s_hit = source_hit(rag_res["retrieved"], q["expected_sources"])
        sec_hit = section_hit(rag_res["retrieved"], q["expected_sections"])

        print(f"  no_rag keyword_coverage={no_rag_cov:.2f} | "
              f"rag keyword_coverage={rag_cov:.2f} | "
              f"source_hit={s_hit} | section_hit={sec_hit}")

        results.append({
            "id": q["id"],
            "question": q["question"],
            "expected_keywords": q["expected_keywords"],
            "expected_sources": q["expected_sources"],
            "expected_sections": q["expected_sections"],
            "no_rag": {
                "text": no_rag["text"],
                "keyword_coverage": no_rag_cov,
                "input_tokens": no_rag["input_tokens"],
                "output_tokens": no_rag["output_tokens"],
                "latency_sec": round(t_no_rag, 2),
            },
            "rag": {
                "text": rag_res["text"],
                "keyword_coverage": rag_cov,
                "source_hit": s_hit,
                "section_hit": sec_hit,
                "retrieved": rag_res["retrieved"],
                "input_tokens": rag_res["input_tokens"],
                "output_tokens": rag_res["output_tokens"],
                "latency_sec": round(t_rag, 2),
            },
        })

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    n = len(results)
    avg_no_rag = sum(r["no_rag"]["keyword_coverage"] for r in results) / n
    avg_rag = sum(r["rag"]["keyword_coverage"] for r in results) / n
    source_hit_rate = sum(r["rag"]["source_hit"] for r in results) / n
    section_hit_rate = sum(r["rag"]["section_hit"] for r in results) / n

    print("\n" + "=" * 60)
    print(f"Средний keyword_coverage без RAG: {avg_no_rag:.2f}")
    print(f"Средний keyword_coverage с RAG:   {avg_rag:.2f}")
    print(f"Source hit rate (RAG):            {source_hit_rate:.2f}")
    print(f"Section hit rate (RAG):           {section_hit_rate:.2f}")
    print(f"\nРезультаты сохранены в {RESULTS_PATH}")


if __name__ == "__main__":
    main()
