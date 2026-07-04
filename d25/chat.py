"""
Мини-чат с RAG + памятью задачи (production-like).

Поверх grounded-RAG из d24 (источники + режим "не знаю") добавлены:
  - история диалога (self.history);
  - "память задачи" (self.task_state): цель диалога, что пользователь уже
    уточнил, зафиксированные ограничения и термины, открытые вопросы;
  - контекстуализация запроса: follow-up вопросы ("а что насчёт этого?")
    переписываются в самостоятельный поисковый запрос с учётом истории и цели;
  - ответ строится с учётом памяти задачи + истории + найденных чанков и
    ВСЕГДА содержит источники.

Каждый ход ask(user_msg):
  1. обновляем task_state (LLM, forced tool) по прошлой памяти + новой реплике;
  2. переписываем вопрос в самостоятельный поисковый запрос (LLM);
  3. retrieval top-K -> пороговый фильтр (как в d24);
  4. если контекст слабый -> "не знаю" (память при этом сохраняется);
  5. иначе grounded-ответ с источниками, с учётом памяти задачи и истории.
"""

import json
import os

import anthropic
import faiss
import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.path.join(BASE, "..", "d21", "data", "index")
STRATEGY = "structure"

OLLAMA_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"

_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
_client = anthropic.Anthropic(api_key=_api_key)
LLM_MODEL = "claude-haiku-4-5"

TOP_K_BEFORE = 10
TOP_K_AFTER = 5
SIM_THRESHOLD = 0.60
HISTORY_TURNS = 6   # сколько последних реплик показываем модели в ответе

IDK_TEXT = (
    "I don't have relevant information in the knowledge base to answer that "
    "reliably. Could you clarify or rephrase?"
)

# ------------------------------------------------------------------ retrieval

def _load_index():
    index = faiss.read_index(os.path.join(INDEX_DIR, f"{STRATEGY}.faiss"))
    with open(os.path.join(INDEX_DIR, f"{STRATEGY}_meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    return index, meta


_INDEX, _META = _load_index()


def embed_query(text: str) -> np.ndarray:
    resp = requests.post(OLLAMA_URL, json={"model": EMBED_MODEL, "input": [text]}, timeout=60)
    resp.raise_for_status()
    vec = np.array(resp.json()["embeddings"], dtype="float32")
    faiss.normalize_L2(vec)
    return vec


def retrieve(query: str, k: int = TOP_K_BEFORE) -> list:
    qvec = embed_query(query)
    scores, ids = _INDEX.search(qvec, k)
    out = []
    for s, i in zip(scores[0], ids[0]):
        if i == -1:
            continue
        c = _META[i]
        out.append({
            "score": float(s), "source": c["source"], "section": c["section"],
            "chunk_id": c["chunk_id"], "text": c["text"],
        })
    return out


def retrieve_multi(queries: list, k: int = TOP_K_BEFORE) -> list:
    """
    Поиск по нескольким запросам (контекстуализованный + исходная реплика) с
    объединением кандидатов по chunk_id и максимальным score. Повышает recall
    для составных follow-up вопросов, когда переписанный запрос дрейфует.
    """
    best = {}
    for q in queries:
        if not q:
            continue
        for c in retrieve(q, k):
            cur = best.get(c["chunk_id"])
            if cur is None or c["score"] > cur["score"]:
                best[c["chunk_id"]] = c
    return sorted(best.values(), key=lambda c: c["score"], reverse=True)


def filter_by_threshold(chunks: list) -> list:
    kept = [c for c in chunks if c["score"] >= SIM_THRESHOLD]
    kept.sort(key=lambda c: c["score"], reverse=True)
    return kept[:TOP_K_AFTER]


def build_context(chunks: list) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        parts.append(
            f"[{i}] source={c['source']} section={c['section']} "
            f"chunk_id={c['chunk_id']}\n{c['text']}"
        )
    return "\n\n".join(parts)


# ------------------------------------------------------------------ LLM tools

# Память задачи: структура, которую модель обновляет каждый ход.
STATE_TOOL = {
    "name": "update_task_state",
    "description": "Update the persistent task memory for the conversation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "The overall goal of the dialogue, refined over time."},
            "clarified": {"type": "array", "items": {"type": "string"},
                          "description": "Facts/preferences the user has clarified so far."},
            "constraints": {"type": "array", "items": {"type": "string"},
                            "description": "Constraints/requirements fixed so far."},
            "glossary": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"term": {"type": "string"}, "definition": {"type": "string"}},
                    "required": ["term", "definition"],
                },
                "description": "Terms explicitly fixed in this dialogue.",
            },
            "open_questions": {"type": "array", "items": {"type": "string"},
                               "description": "Things still to resolve."},
        },
        "required": ["goal", "clarified", "constraints", "glossary", "open_questions"],
    },
}

ANSWER_TOOL = {
    "name": "grounded_reply",
    "description": "Reply grounded in the retrieved context, always listing sources.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "section": {"type": "string"},
                        "chunk_id": {"type": "string"},
                    },
                    "required": ["source", "section", "chunk_id"],
                },
            },
        },
        "required": ["answer", "sources"],
    },
}

SYSTEM_STATE = (
    "You maintain the task memory of an ongoing assistant<->user dialogue about "
    "Retrieval-Augmented Generation (RAG). Given the CURRENT memory and the new "
    "user message, return the UPDATED memory via the tool `update_task_state`.\n"
    "Rules: when the user explicitly states their goal (e.g. 'my goal is to ...'), "
    "capture THAT overarching objective as `goal`, not a narrower sub-question "
    "they happen to ask in the same message. Keep the `goal` stable once "
    "established — refine wording only, never drop or replace it unless the user "
    "explicitly changes it. Accumulate clarified facts, constraints and fixed "
    "terms; do not erase earlier items unless contradicted. Be concise."
)

SYSTEM_REWRITE = (
    "Rewrite the user's LATEST message into a single, focused standalone search "
    "query for semantic retrieval over RAG research papers. Use the conversation "
    "ONLY to resolve pronouns and follow-up references (e.g. 'those', 'as we "
    "defined it'); do NOT pile in topics from earlier turns that the latest "
    "message is not about. Keep the query about what the latest message actually "
    "asks. Output ONLY the query text, in English, no explanation."
)

SYSTEM_ANSWER = (
    "You are a helpful assistant in an ongoing dialogue about RAG. Answer the "
    "user's latest message using ONLY the retrieved context chunks, while staying "
    "consistent with the TASK MEMORY (goal, clarified facts, constraints, fixed "
    "terms). Never lose sight of the goal. You MUST call `grounded_reply`.\n"
    "Answer with whatever the context supports, even if it only partially covers "
    "the message, and list EVERY source you drew on (source, section, chunk_id). "
    "If you use a chunk's content — even by paraphrasing it — you MUST list it as "
    "a source. Return empty sources ONLY when the chunks are genuinely unrelated "
    "to the message and contain no usable information; in that case say so plainly "
    "in `answer`. For pure memory-recall messages (e.g. 'what is our goal?') answer "
    "from the task memory and empty sources are fine. Answer in English."
)


def _call_tool(system: str, messages: list, tool: dict, max_tokens: int = 900) -> tuple:
    resp = _client.messages.create(
        model=LLM_MODEL, max_tokens=max_tokens, system=system,
        tools=[tool], tool_choice={"type": "tool", "name": tool["name"]},
        messages=messages,
    )
    tu = next((b for b in resp.content if b.type == "tool_use"), None)
    return (tu.input if tu else {}), resp.usage.input_tokens, resp.usage.output_tokens


# ------------------------------------------------------------------ session

class ChatSession:
    def __init__(self):
        self.history = []  # [{role, content}]
        self.task_state = {
            "goal": "", "clarified": [], "constraints": [],
            "glossary": [], "open_questions": [],
        }
        self.turns = []  # структурированный лог ходов (для проверки/визуализации)

    # --- 1. память задачи -------------------------------------------------
    @staticmethod
    def _union(old: list, new: list) -> list:
        """Накопительное объединение списков строк (без дублей, порядок сохраняется)."""
        seen = {x.strip().lower() for x in old}
        merged = list(old)
        for x in new or []:
            if x.strip().lower() not in seen:
                merged.append(x)
                seen.add(x.strip().lower())
        return merged

    @staticmethod
    def _merge_glossary(old: list, new: list) -> list:
        """Слияние по term: новые определения обновляют, старые термины не теряются."""
        by_term = {g["term"].strip().lower(): g for g in old}
        for g in new or []:
            by_term[g["term"].strip().lower()] = g
        return list(by_term.values())

    def _update_state(self, user_msg: str):
        payload = (
            f"CURRENT MEMORY:\n{json.dumps(self.task_state, ensure_ascii=False, indent=2)}\n\n"
            f"NEW USER MESSAGE:\n{user_msg}"
        )
        data, _, _ = _call_tool(SYSTEM_STATE, [{"role": "user", "content": payload}], STATE_TOOL, 700)
        if data:
            prev = self.task_state
            goal = data.get("goal") or prev["goal"]  # пустую цель не принимаем
            # clarified/constraints/glossary — накопительные на уровне кода,
            # чтобы память задачи не "сжималась", даже если модель их не перечислит;
            # open_questions наоборот могут закрываться, поэтому берём как есть.
            self.task_state = {
                "goal": goal,
                "clarified": self._union(prev["clarified"], data.get("clarified", [])),
                "constraints": self._union(prev["constraints"], data.get("constraints", [])),
                "glossary": self._merge_glossary(prev["glossary"], data.get("glossary", [])),
                "open_questions": data.get("open_questions", []),
            }

    # --- 2. контекстуализация запроса ------------------------------------
    def _contextualize(self, user_msg: str) -> str:
        recent = self.history[-HISTORY_TURNS:]
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
        payload = (
            f"GOAL: {self.task_state['goal']}\n\n"
            f"CONVERSATION SO FAR:\n{convo}\n\n"
            f"LATEST USER MESSAGE:\n{user_msg}"
        )
        resp = _client.messages.create(
            model=LLM_MODEL, max_tokens=100, system=SYSTEM_REWRITE,
            messages=[{"role": "user", "content": payload}],
        )
        return resp.content[0].text.strip().strip('"')

    # --- 3-5. основной ход -----------------------------------------------
    def ask(self, user_msg: str) -> dict:
        self._update_state(user_msg)
        search_query = self._contextualize(user_msg)

        # ищем и по переписанному запросу, и по исходной реплике — на случай,
        # если rewrite увёл поиск в сторону (составные follow-up вопросы)
        retrieved = retrieve_multi([search_query, user_msg], TOP_K_BEFORE)
        kept = filter_by_threshold(retrieved)

        state_str = json.dumps(self.task_state, ensure_ascii=False, indent=2)

        if not kept:
            # контекст ниже порога -> честный режим "не знаю" (как в d24)
            answer_text, sources = IDK_TEXT, []
            idk = True
        else:
            recent = self.history[-HISTORY_TURNS:]
            context = build_context(kept)
            payload = (
                f"TASK MEMORY:\n{state_str}\n\n"
                f"RETRIEVED CONTEXT:\n{context}\n\n"
                f"USER MESSAGE:\n{user_msg}"
            )
            messages = recent + [{"role": "user", "content": payload}]
            data, _, _ = _call_tool(SYSTEM_ANSWER, messages, ANSWER_TOOL)
            answer_text = data.get("answer", "")
            sources = data.get("sources", []) or []
            # ответ дан (в т.ч. из памяти задачи, если это вопрос-напоминание);
            # пустые sources тут не означают "не знаю"
            idk = False

        # обновляем историю (в историю кладём чистую реплику пользователя и ответ)
        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": answer_text})

        turn = {
            "user": user_msg,
            "search_query": search_query,
            "answer": answer_text,
            "sources": sources,
            "idk": idk,
            "n_kept": len(kept),
            "task_state": json.loads(state_str),  # снимок памяти на этот ход
        }
        self.turns.append(turn)
        return turn


if __name__ == "__main__":
    s = ChatSession()
    for q in [
        "I'm building a production RAG pipeline over research papers. My goal is to understand the full pipeline. What chunking strategies should I consider?",
        "We'll use fixed-size chunking with overlap. What re-ranking techniques exist in the post-retrieval stage?",
        "Remind me — what is our goal and what have we fixed so far?",
    ]:
        t = s.ask(q)
        print(f"\nUSER: {q}\nQUERY: {t['search_query']}\nANSWER: {t['answer'][:200]}")
        print("SOURCES:", [f"{x['source']}|{x['section']}" for x in t["sources"]])
    print("\nFINAL TASK STATE:", json.dumps(s.task_state, ensure_ascii=False, indent=2))
