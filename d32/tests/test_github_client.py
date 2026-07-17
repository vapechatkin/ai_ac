import json

import httpx

from github_client import GitHubClient, REVIEW_MARKER


def response(request: httpx.Request, status: int, payload=None, text: str = ""):
    if payload is not None:
        return httpx.Response(status, json=payload, request=request)
    return httpx.Response(status, text=text, request=request)


def test_get_pull_request_collects_files_and_diff() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/app/pulls/7/files":
            return response(
                request,
                200,
                [
                    {
                        "filename": "src/app.py",
                        "status": "modified",
                        "additions": 3,
                        "deletions": 1,
                        "changes": 4,
                        "patch": "@@ -1 +1 @@\n-old\n+new",
                    }
                ],
            )
        if path == "/repos/acme/app/pulls/7" and "diff" in request.headers.get(
            "accept", ""
        ):
            return response(request, 200, text="diff --git a/src/app.py b/src/app.py")
        if path == "/repos/acme/app/pulls/7":
            return response(
                request,
                200,
                {
                    "title": "Fix app",
                    "body": "Fixes an edge case",
                    "html_url": "https://github.com/acme/app/pull/7",
                    "base": {"sha": "base123"},
                    "head": {
                        "sha": "head456",
                        "repo": {"full_name": "alice/app-fork"},
                    },
                    "user": {"login": "alice"},
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    http = httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    )
    client = GitHubClient("token", client=http)

    pr = client.get_pull_request("acme/app", 7)

    assert pr.title == "Fix app"
    assert pr.head_repository == "alice/app-fork"
    assert pr.changed_paths == ("src/app.py",)
    assert pr.diff.startswith("diff --git")
    assert pr.files[0].additions == 3


def test_upsert_updates_existing_bot_comment() -> None:
    requests: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode() if request.content else ""
        requests.append((request.method, request.url.path, body))
        if request.url.path.endswith("/issues/7/comments"):
            return response(
                request,
                200,
                [
                    {
                        "id": 42,
                        "body": f"{REVIEW_MARKER}\nold",
                        "user": {"type": "Bot"},
                    }
                ],
            )
        if request.url.path.endswith("/issues/comments/42"):
            return response(request, 200, {"id": 42})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    http = httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    )
    client = GitHubClient("token", client=http)

    action, comment_id = client.upsert_review_comment("acme/app", 7, "new review")

    assert (action, comment_id) == ("updated", 42)
    patch = next(item for item in requests if item[0] == "PATCH")
    assert REVIEW_MARKER in json.loads(patch[2])["body"]
    assert "new review" in json.loads(patch[2])["body"]


def test_human_marker_does_not_hijack_bot_comment() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return response(
                request,
                200,
                [
                    {
                        "id": 5,
                        "body": REVIEW_MARKER,
                        "user": {"type": "User"},
                    }
                ],
            )
        if request.method == "POST":
            return response(request, 201, {"id": 99})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    http = httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    )
    client = GitHubClient("token", client=http)

    assert client.upsert_review_comment("acme/app", 7, "review") == ("created", 99)
