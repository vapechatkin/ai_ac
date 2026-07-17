from pathlib import Path

from github_client import ChangedFile, PullRequestContext
from rag import RAGIndex, build_retrieval_query, classify_path, discover_project_files


def make_pr() -> PullRequestContext:
    return PullRequestContext(
        repository="acme/app",
        head_repository="alice/app-fork",
        number=1,
        title="Fix authentication token refresh",
        body="Handle expired access tokens",
        html_url="https://example.test/pr/1",
        base_sha="base",
        head_sha="head",
        author="alice",
        files=(
            ChangedFile(
                filename="src/auth.py",
                status="modified",
                additions=2,
                deletions=1,
                changes=3,
                patch="@@ -10 +10 @@\n-old_token\n+refresh_token",
            ),
        ),
        diff="diff --git a/src/auth.py b/src/auth.py",
    )


def test_classification_covers_docs_code_and_ignores_locks() -> None:
    assert classify_path(Path("README.md")) == "documentation"
    assert classify_path(Path("docs/openapi.yaml")) == "documentation"
    assert classify_path(Path("src/auth.py")) == "code"
    assert classify_path(Path("package-lock.json")) is None
    assert classify_path(Path("build/generated.py")) is None


def test_rag_balances_documentation_and_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Authentication\nRefresh expired authentication tokens safely.", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text(
        "def refresh_token(token):\n    return token.rotate()", encoding="utf-8"
    )
    index, source_count = RAGIndex.build(
        tmp_path,
        {"src/auth.py": "def refresh_token(token):\n    validate(token)\n    return rotate(token)"},
    )

    results = index.balanced_search(build_retrieval_query(make_pr()))

    assert source_count == 2
    assert {result.chunk.kind for result in results} == {"documentation", "code"}
    assert any(result.chunk.path == "src/auth.py" for result in results)


def test_discovery_skips_build_output(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "generated.py").write_text("secret = 1", encoding="utf-8")

    paths = [item.relative_to(tmp_path).as_posix() for item in discover_project_files(tmp_path)]

    assert paths == ["main.py"]
