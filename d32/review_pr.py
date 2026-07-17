#!/usr/bin/env python3
"""GitHub Action entry point for automatic RAG-assisted PR review."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from github_client import GitHubClient
from rag import RAGIndex, build_retrieval_query, classify_path, format_rag_context
from reviewer import ClaudeReviewer, render_review_comment


BASE_DIR = Path(__file__).resolve().parent
MAX_HEAD_FILES = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG-assisted AI review for a GitHub PR")
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", type=int, default=_environment_int("PR_NUMBER"))
    parser.add_argument("--workspace", default=os.getenv("GITHUB_WORKSPACE", str(Path.cwd())))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _environment_int(name: str) -> int | None:
    raw = os.getenv(name)
    return int(raw) if raw and raw.isdigit() else None


def validate_inputs(repository: str | None, pr_number: int | None, workspace: Path) -> None:
    if not repository or repository.count("/") != 1:
        raise ValueError("Передайте --repo owner/repository или GITHUB_REPOSITORY")
    if pr_number is None or pr_number <= 0:
        raise ValueError("Передайте положительный --pr или PR_NUMBER")
    if not workspace.is_dir():
        raise ValueError(f"Workspace не найден: {workspace}")


def collect_changed_contents(client: GitHubClient, pr) -> dict[str, str]:
    contents: dict[str, str] = {}
    candidates = [
        file
        for file in pr.files
        if file.status != "removed" and classify_path(Path(file.filename)) is not None
    ]
    for file in candidates[:MAX_HEAD_FILES]:
        content = client.get_file_content(
            pr.head_repository, file.filename, pr.head_sha
        )
        if content is not None:
            contents[file.filename] = content
    return contents


def run() -> int:
    load_dotenv(BASE_DIR / ".env")
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    try:
        validate_inputs(args.repo, args.pr, workspace)
        token = os.getenv("GITHUB_TOKEN", "").strip()
        with GitHubClient(token) as github:
            print(f"Получаю PR #{args.pr} и diff через GitHub API…")
            pr = github.get_pull_request(args.repo, args.pr)
            print(f"Изменено файлов: {len(pr.files)}, diff: {len(pr.diff)} символов")

            changed_contents = collect_changed_contents(github, pr)
            index, source_count = RAGIndex.build(workspace, changed_contents)
            query = build_retrieval_query(pr)
            results = index.balanced_search(query)
            rag_context = format_rag_context(results)
            print(
                f"RAG: {source_count} файлов, {len(index.chunks)} фрагментов, "
                f"в контекст выбрано {len(results)}"
            )

            reviewer = ClaudeReviewer()
            review = reviewer.review(pr, rag_context)
            comment = render_review_comment(pr, review, reviewer.model)
            if args.dry_run:
                print("\n--- DRY RUN: комментарий не опубликован ---\n")
                print(comment)
                return 0

            action, comment_id = github.upsert_review_comment(
                args.repo, args.pr, comment
            )
            print(f"PR-комментарий {action}: id={comment_id}")
            return 0
    except Exception as exc:
        print(f"AI review failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
