"""
Прогон 2 длинных сценариев (по 10-15 сообщений) через ChatSession и проверка:

  1. источники на content-ходах — на каждом knowledge-ходе ассистент выдаёт
     ответ с источниками (>=1);
  2. удержание цели — снимок task_state.goal на каждом ходе остаётся
     согласованным с изначальной целью сценария (LLM-судья, батч на сценарий);
  3. память задачи — на memory-ходах ассистент правильно воспроизводит цель
     и зафиксированное (LLM-судья по каждому такому ходу);
  4. рост памяти — сколько clarified/constraints/glossary накопилось к концу.

Результат -> results.json.
"""

import json
import os
import re

import chat

BASE = os.path.dirname(os.path.abspath(__file__))
SCENARIOS_PATH = os.path.join(BASE, "scenarios.json")
RESULTS_PATH = os.path.join(BASE, "results.json")


def _judge(system: str, user: str, max_tokens: int = 300) -> str:
    resp = chat._client.messages.create(
        model=chat.LLM_MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def judge_goal_retention(intended_goal: str, per_turn_goals: list) -> list:
    """Возвращает список 0/1: согласуется ли goal каждого хода с целью сценария."""
    system = (
        "You check whether a tracked GOAL stays consistent with the INTENDED goal "
        "across dialogue turns. For each turn goal, output 1 if it is the same "
        "underlying goal (wording may differ / be refined) and 0 if the goal was "
        "lost, replaced, or emptied. Reply STRICTLY as a JSON array of 0/1 with the "
        "same length as the input list."
    )
    listing = "\n".join(f"[{i}] {g!r}" for i, g in enumerate(per_turn_goals))
    user = f"INTENDED GOAL:\n{intended_goal}\n\nTURN GOALS:\n{listing}"
    text = _judge(system, user)
    m = re.search(r"\[[\s\d,]*\]", text)
    if not m:
        return [0] * len(per_turn_goals)
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [0] * len(per_turn_goals)
    arr = (arr + [0] * len(per_turn_goals))[:len(per_turn_goals)]
    return [1 if x else 0 for x in arr]


def judge_memory_recall(intended_goal: str, answer: str) -> bool:
    """На memory-ходе: правильно ли ассистент воспроизвёл цель диалога."""
    system = (
        "Does the ASSISTANT ANSWER correctly restate the INTENDED goal of the "
        "dialogue (same underlying objective)? Reply STRICTLY as JSON "
        '{"recalled": true|false}.'
    )
    user = f"INTENDED GOAL:\n{intended_goal}\n\nASSISTANT ANSWER:\n{answer}"
    text = _judge(system, user, 100)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return False
    try:
        return bool(json.loads(m.group(0)).get("recalled", False))
    except json.JSONDecodeError:
        return False


def run_scenario(scn: dict) -> dict:
    session = chat.ChatSession()
    intended = scn["intended_goal"]
    turns_out = []

    print(f"\n### {scn['name']}")
    print(f"    цель: {intended}")
    for i, msg in enumerate(scn["messages"], start=1):
        turn = session.ask(msg["text"])
        kind = msg["type"]
        has_sources = len(turn["sources"]) >= 1

        rec = {
            "i": i, "type": kind,
            "user": msg["text"],
            "search_query": turn["search_query"],
            "answer": turn["answer"],
            "sources": turn["sources"],
            "has_sources": has_sources,
            "idk": turn["idk"],
            "goal_snapshot": turn["task_state"]["goal"],
            "n_clarified": len(turn["task_state"]["clarified"]),
            "n_constraints": len(turn["task_state"]["constraints"]),
            "n_glossary": len(turn["task_state"]["glossary"]),
        }
        if kind == "memory":
            rec["memory_recall_ok"] = judge_memory_recall(intended, turn["answer"])
        turns_out.append(rec)

        tag = "K" if kind == "knowledge" else "M"
        extra = f" recall={rec.get('memory_recall_ok')}" if kind == "memory" else ""
        print(f"  [{i:2d}{tag}] src={has_sources} nsrc={len(turn['sources'])}{extra} "
              f"| goal='{turn['task_state']['goal'][:45]}...'")

    # удержание цели по всем ходам
    goals = [t["goal_snapshot"] for t in turns_out]
    retention = judge_goal_retention(intended, goals)
    for t, r in zip(turns_out, retention):
        t["goal_consistent"] = bool(r)

    knowledge = [t for t in turns_out if t["type"] == "knowledge"]
    memory = [t for t in turns_out if t["type"] == "memory"]
    summary = {
        "n_messages": len(turns_out),
        "n_knowledge": len(knowledge),
        "n_memory": len(memory),
        "sources_on_knowledge_rate": round(sum(t["has_sources"] for t in knowledge) / (len(knowledge) or 1), 2),
        "goal_retention_rate": round(sum(retention) / (len(retention) or 1), 2),
        "memory_recall_rate": round(sum(t["memory_recall_ok"] for t in memory) / (len(memory) or 1), 2),
        "final_clarified": turns_out[-1]["n_clarified"],
        "final_constraints": turns_out[-1]["n_constraints"],
        "final_glossary": turns_out[-1]["n_glossary"],
    }
    return {
        "name": scn["name"], "intended_goal": intended,
        "final_task_state": session.task_state,
        "turns": turns_out, "summary": summary,
    }


def main():
    with open(SCENARIOS_PATH, encoding="utf-8") as f:
        scenarios = json.load(f)

    results = [run_scenario(scn) for scn in scenarios]

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 64)
    for r in results:
        s = r["summary"]
        print(f"\n{r['name']}")
        print(f"  источники на knowledge-ходах : {s['sources_on_knowledge_rate']*100:.0f}% "
              f"({sum(t['has_sources'] for t in r['turns'] if t['type']=='knowledge')}/{s['n_knowledge']})")
        print(f"  удержание цели (все ходы)     : {s['goal_retention_rate']*100:.0f}% "
              f"({sum(t['goal_consistent'] for t in r['turns'])}/{s['n_messages']})")
        print(f"  память: цель на memory-ходах  : {s['memory_recall_rate']*100:.0f}% "
              f"({sum(t.get('memory_recall_ok', False) for t in r['turns'])}/{s['n_memory']})")
        print(f"  накоплено памяти к концу      : clarified={s['final_clarified']} "
              f"constraints={s['final_constraints']} glossary={s['final_glossary']}")

    print(f"\nРезультаты сохранены в {RESULTS_PATH}")


if __name__ == "__main__":
    main()
