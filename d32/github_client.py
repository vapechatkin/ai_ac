"""Minimal GitHub REST client for reading a PR and upserting its review comment."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
REVIEW_MARKER = "<!-- d32-ai-review -->"
MAX_DIFF_CHARS = 80_000
MAX_FILE_CONTENT_CHARS = 40_000


@dataclass(frozen=True)
class ChangedFile:
    filename: str
    status: str
    additions: int
    deletions: int
    changes: int
    patch: str
    previous_filename: str | None = None


@dataclass(frozen=True)
class PullRequestContext:
    repository: str
    head_repository: str
    number: int
    title: str
    body: str
    html_url: str
    base_sha: str
    head_sha: str
    author: str
    files: tuple[ChangedFile, ...]
    diff: str

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(file.filename for file in self.files)


class GitHubClient:
    def __init__(self, token: str, client: httpx.Client | None = None) -> None:
        if not token.strip():
            raise ValueError("Не задан GITHUB_TOKEN")
        self._owns_client = client is None
        self.client = client or httpx.Client(
            base_url=API_ROOT,
            timeout=60.0,
            follow_redirects=True,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "d32-ai-review",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_pull_request(self, repository: str, number: int) -> PullRequestContext:
        pull = self._json("GET", f"/repos/{repository}/pulls/{number}")
        files = self.list_pull_files(repository, number)
        diff = self.get_pull_diff(repository, number)
        return PullRequestContext(
            repository=repository,
            head_repository=str(pull["head"]["repo"]["full_name"]),
            number=number,
            title=str(pull["title"]),
            body=str(pull.get("body") or ""),
            html_url=str(pull["html_url"]),
            base_sha=str(pull["base"]["sha"]),
            head_sha=str(pull["head"]["sha"]),
            author=str(pull["user"]["login"]),
            files=tuple(files),
            diff=_truncate(diff, MAX_DIFF_CHARS, "diff обрезан по лимиту"),
        )

    def list_pull_files(self, repository: str, number: int) -> list[ChangedFile]:
        files: list[ChangedFile] = []
        page = 1
        while True:
            payload = self._json(
                "GET",
                f"/repos/{repository}/pulls/{number}/files",
                params={"per_page": 100, "page": page},
            )
            if not isinstance(payload, list):
                raise RuntimeError("GitHub вернул неожиданный список файлов")
            for raw in payload:
                files.append(
                    ChangedFile(
                        filename=str(raw["filename"]),
                        previous_filename=(
                            str(raw["previous_filename"])
                            if raw.get("previous_filename")
                            else None
                        ),
                        status=str(raw["status"]),
                        additions=int(raw.get("additions", 0)),
                        deletions=int(raw.get("deletions", 0)),
                        changes=int(raw.get("changes", 0)),
                        patch=_truncate(
                            str(raw.get("patch") or ""),
                            MAX_FILE_CONTENT_CHARS,
                            "patch файла обрезан",
                        ),
                    )
                )
            if len(payload) < 100:
                break
            page += 1
        return files

    def get_pull_diff(self, repository: str, number: int) -> str:
        response = self.client.get(
            f"/repos/{repository}/pulls/{number}",
            headers={"Accept": "application/vnd.github.diff"},
        )
        response.raise_for_status()
        return response.text

    def get_file_content(self, repository: str, path: str, ref: str) -> str | None:
        """Read a text file through GitHub without executing PR code."""
        encoded_path = quote(path, safe="/")
        response = self.client.get(
            f"/repos/{repository}/contents/{encoded_path}", params={"ref": ref}
        )
        if response.status_code in {404, 422}:
            return None
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("encoding") != "base64":
            return None
        try:
            data = base64.b64decode(str(payload["content"]), validate=False)
            return data.decode("utf-8", errors="replace")[:MAX_FILE_CONTENT_CHARS]
        except (KeyError, ValueError):
            return None

    def upsert_review_comment(
        self, repository: str, number: int, review_body: str
    ) -> tuple[str, int]:
        body = f"{REVIEW_MARKER}\n{review_body}"[:65_000]
        comments = self._all_issue_comments(repository, number)
        existing = next(
            (
                comment
                for comment in comments
                if REVIEW_MARKER in str(comment.get("body") or "")
                and str(comment.get("user", {}).get("type")) == "Bot"
            ),
            None,
        )
        if existing is not None:
            comment_id = int(existing["id"])
            self._json(
                "PATCH",
                f"/repos/{repository}/issues/comments/{comment_id}",
                json={"body": body},
            )
            return "updated", comment_id

        created = self._json(
            "POST",
            f"/repos/{repository}/issues/{number}/comments",
            json={"body": body},
        )
        return "created", int(created["id"])

    def _all_issue_comments(self, repository: str, number: int) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._json(
                "GET",
                f"/repos/{repository}/issues/{number}/comments",
                params={"per_page": 100, "page": page},
            )
            if not isinstance(payload, list):
                raise RuntimeError("GitHub вернул неожиданный список комментариев")
            comments.extend(item for item in payload if isinstance(item, dict))
            if len(payload) < 100:
                break
            page += 1
        return comments


def _truncate(text: str, limit: int, note: str) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [{note}]"
