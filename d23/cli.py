"""
Интерактивный CLI: 4 режима RAG (+ no-RAG) на выбор.

По умолчанию на каждый вопрос показывает все режимы сразу — удобно для
сравнения на видео. Можно ограничиться одним режимом через :mode <вопрос>.

Режимы: no_rag, baseline, threshold, llm_rerank, rewrite_filter
"""

import sys

import rag2


def print_result(label: str, result: dict):
    print(f"\n--- {label} ---")
    if "rewritten_query" in result:
        print(f"[переформулированный запрос: {result['rewritten_query']}]")
    print(result["text"])
    if result["retrieved"]:
        print(f"\nретрив {len(result['retrieved'])} -> оставлено {len(result['kept'])}:")
        for c in result["retrieved"]:
            mark = "OK " if c in result["kept"] else "  x"
            extra = f" rerank={c['rerank_score']}" if "rerank_score" in c else ""
            print(f"  {mark} score={c['score']:.3f}{extra} | {c['source']} | {c['section']}")


def main():
    print("Агент с 4 режимами RAG + no-RAG:", list(rag2.MODES))
    print("Ввод: вопрос (все режимы) | :<mode> вопрос (один режим) | exit\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line or line.lower() in ("exit", "quit", "q"):
            break

        matched_mode = None
        for mode in rag2.MODES:
            prefix = f":{mode} "
            if line.startswith(prefix):
                matched_mode = mode
                question = line[len(prefix):].strip()
                break

        if matched_mode:
            print_result(matched_mode.upper(), rag2.answer(question, matched_mode))
        else:
            question = line
            for mode in rag2.MODES:
                print_result(mode.upper(), rag2.answer(question, mode))
        print()


if __name__ == "__main__":
    sys.exit(main())
