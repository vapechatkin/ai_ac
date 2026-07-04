"""
Проверка grounded-RAG (rag3.answer) на 10 контрольных вопросах + отдельный
блок вопросов вне корпуса для проверки режима "не знаю".

Три обязательные проверки задания (по каждому ответу):
  has_sources          — есть ли источники (>=1)
  has_citations        — есть ли цитаты (>=1)
  citations_grounded   — доля цитат, дословно найденных в kept-чанках
                         (защита от выдуманных цитат)
  answer_matches_cites — совпадает ли СМЫСЛ ответа с цитатами (LLM-судья,
                         faithfulness/entailment, порог score>=7)

Плюс прежние эвристики для преемственности с d22/d23:
  keyword_coverage, source_hit, section_hit.

Блок "не знаю": на вопросах вне корпуса ожидаем idk=True и пустые
sources/citations.

Результат -> results.json.
"""

import json
import os
import re
import time

import rag3

BASE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_PATH = os.path.join(BASE, "questions.json")
RESULTS_PATH = os.path.join(BASE, "results.json")

# Вопросы заведомо вне корпуса (корпус — только статьи про RAG).
OFF_TOPIC = [
    "What is the capital of France?",
    "How do I bake a chocolate cake?",
    "Who won the 2018 FIFA World Cup?",
]

FAITHFULNESS_MIN = 7  # порог LLM-судьи для answer_matches_citations

JUDGE_SYSTEM = (
    "You are a strict evaluator of faithfulness. Given an ANSWER and a set of "
    "CITATIONS (quotes), decide whether the answer's meaning is fully supported "
    "by the citations — i.e. every claim in the answer can be traced to the "
    "citations, with no invented facts. Reply STRICTLY as a JSON object: "
    '{"score": <0-10 integer>, "reason": "<short>"}. '
    "10 = fully supported, 0 = contradicts or unsupported."
)


def _norm(text: str) -> str:
    # де-переносы: в PDF-чанках слова разорваны как "knowl-\nedge"; модель
    # цитирует их слитно ("knowledge"), поэтому склеиваем перед сравнением.
    text = re.sub(r"-\s*\n\s*", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def citations_grounded(citations: list, kept: list) -> float:
    """Доля цитат, дословно (по нормализованному тексту) найденных в чанках."""
    if not citations:
        return 0.0
    kept_norm = [_norm(c["text"]) for c in kept]
    hits = 0
    for cit in citations:
        q = _norm(cit.get("quote", ""))
        if q and any(q in kt for kt in kept_norm):
            hits += 1
    return hits / len(citations)


def judge_faithfulness(answer: str, citations: list) -> dict:
    if not citations:
        return {"score": 0, "reason": "no citations"}
    cites = "\n".join(f'- "{c.get("quote", "")}"' for c in citations)
    user = f"ANSWER:\n{answer}\n\nCITATIONS:\n{cites}"
    resp = rag3._client.messages.create(
        model=rag3.LLM_MODEL, max_tokens=200, system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text = resp.content[0].text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"score": 0, "reason": "unparseable judge output"}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"score": 0, "reason": "unparseable judge output"}


def keyword_coverage(text: str, keywords: list) -> float:
    if not keywords:
        return 1.0
    low = text.lower()
    return sum(1 for kw in keywords if kw.lower() in low) / len(keywords)


def source_hit(sources: list, expected: list) -> bool:
    return any(s.get("source") in expected for s in sources)


def section_hit(sources: list, expected: list) -> bool:
    exp_low = [s.lower() for s in expected]
    for s in sources:
        sec = (s.get("section") or "").lower()
        if sec and any(e in sec or sec in e for e in exp_low):
            return True
    return False


def eval_question(q: dict) -> dict:
    t0 = time.time()
    r = rag3.answer(q["question"])
    latency = round(time.time() - t0, 2)

    has_sources = len(r["sources"]) >= 1
    has_citations = len(r["citations"]) >= 1
    grounded = citations_grounded(r["citations"], r["kept"])
    judge = judge_faithfulness(r["answer"], r["citations"])
    faithful = judge.get("score", 0) >= FAITHFULNESS_MIN

    return {
        "id": q["id"], "question": q["question"],
        "answer": r["answer"],
        "sources": r["sources"],
        "citations": r["citations"],
        "idk": r["idk"], "idk_reason": r["idk_reason"],
        "n_retrieved": len(r["retrieved"]), "n_kept": len(r["kept"]),
        # обязательные проверки задания
        "has_sources": has_sources,
        "has_citations": has_citations,
        "citations_grounded": round(grounded, 2),
        "answer_matches_citations": faithful,
        "faithfulness_score": judge.get("score", 0),
        "faithfulness_reason": judge.get("reason", ""),
        # преемственность с d22/d23
        "keyword_coverage": round(keyword_coverage(r["answer"], q["expected_keywords"]), 2),
        "source_hit": source_hit(r["sources"], q["expected_sources"]),
        "section_hit": section_hit(r["sources"], q["expected_sections"]),
        "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"],
        "latency_sec": latency,
    }


def eval_off_topic(question: str) -> dict:
    r = rag3.answer(question)
    return {
        "question": question,
        "idk": r["idk"], "idk_reason": r["idk_reason"],
        "n_kept": len(r["kept"]),
        "has_sources": len(r["sources"]) >= 1,
        "has_citations": len(r["citations"]) >= 1,
        "answer": r["answer"],
    }


def main():
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        questions = json.load(f)

    on_topic = []
    print("=== 10 контрольных вопросов (grounded) ===")
    for q in questions:
        e = eval_question(q)
        on_topic.append(e)
        print(f"[{e['id']:2d}] src={e['has_sources']} cite={e['has_citations']} "
              f"grounded={e['citations_grounded']:.2f} "
              f"faithful={e['answer_matches_citations']}({e['faithfulness_score']}) "
              f"idk={e['idk']}")

    print("\n=== Вопросы вне корпуса (режим 'не знаю') ===")
    off_topic = []
    for question in OFF_TOPIC:
        e = eval_off_topic(question)
        off_topic.append(e)
        print(f"  idk={e['idk']} kept={e['n_kept']} | {question}")

    n = len(on_topic)
    # Метрики источников/цитат честно считаем по ОТВЕЧЕННЫМ вопросам: у ответа
    # в режиме "не знаю" источников и цитат не должно быть по определению.
    answered = [e for e in on_topic if not e["idk"]]
    na = len(answered) or 1

    def _rate(items, key):
        return round(sum(e[key] for e in items) / (len(items) or 1), 2)

    summary = {
        "n_questions": n,
        "n_answered": len(answered),
        "n_idk": n - len(answered),
        # среди отвеченных: обязательные проверки задания
        "answered_sources_rate": _rate(answered, "has_sources"),
        "answered_citations_rate": _rate(answered, "has_citations"),
        "answered_citations_grounded_avg": _rate(answered, "citations_grounded"),
        "answered_matches_citations_rate": _rate(answered, "answer_matches_citations"),
        "answered_faithfulness_avg": _rate(answered, "faithfulness_score"),
        # преемственность с d22/d23 (по всем 10)
        "keyword_coverage_avg": _rate(on_topic, "keyword_coverage"),
        "source_hit_rate": _rate(on_topic, "source_hit"),
        "section_hit_rate": _rate(on_topic, "section_hit"),
        # режим "не знаю"
        "off_topic_total": len(off_topic),
        "off_topic_idk": sum(e["idk"] for e in off_topic),
    }

    out = {"summary": summary, "on_topic": on_topic, "off_topic": off_topic}
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 62)
    print(f"отвечено / 'не знаю'       : {len(answered)} / {n - len(answered)} "
          f"(из {n} вопросов)")
    print(f"источники в каждом ответе  : {summary['answered_sources_rate']*100:.0f}% "
          f"({sum(e['has_sources'] for e in answered)}/{len(answered)} отвеченных)")
    print(f"цитаты в каждом ответе     : {summary['answered_citations_rate']*100:.0f}% "
          f"({sum(e['has_citations'] for e in answered)}/{len(answered)} отвеченных)")
    print(f"цитаты дословно из чанков   : {summary['answered_citations_grounded_avg']*100:.0f}% (в среднем)")
    print(f"смысл ответа == цитаты      : {summary['answered_matches_citations_rate']*100:.0f}% "
          f"(судья, avg score={summary['answered_faithfulness_avg']})")
    print(f"'не знаю' вне корпуса       : {summary['off_topic_idk']}/{summary['off_topic_total']}")
    print(f"\nРезультаты сохранены в {RESULTS_PATH}")


if __name__ == "__main__":
    main()
