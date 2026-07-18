from pathlib import Path

import pytest

import mcp_server


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src" / "api.py").write_text("class BillingAPI:\n    pass\n", encoding="utf-8")
    (tmp_path / "src" / "service.py").write_text("from api import BillingAPI\n", encoding="utf-8")
    (tmp_path / "docs" / "api.md").write_text("# Billing\n\nBillingAPI docs.\n", encoding="utf-8")
    monkeypatch.setattr(mcp_server, "ROOT", tmp_path)
    mcp_server._originals.clear()
    return tmp_path


def test_lists_searches_and_reads_multiple_files(project: Path) -> None:
    listing = mcp_server.list_files()
    assert listing["total"] == 3

    result = mcp_server.search_text("BillingAPI")
    assert {match["path"] for match in result["matches"]} == {
        "docs/api.md", "src/api.py", "src/service.py"
    }

    read = mcp_server.read_files(["src/api.py", "docs/api.md"])
    assert len(read["files"]) == 2
    assert "1: class BillingAPI:" in read["files"][0]["content"]


def test_write_is_idempotent_and_produces_diff(project: Path) -> None:
    content = "# Billing\n\nCurrent BillingAPI documentation.\n"
    first = mcp_server.write_file("docs/api.md", content)
    second = mcp_server.write_file("docs/api.md", content)
    diff = mcp_server.diff_changes()

    assert first["changed"] is True
    assert second["changed"] is False
    assert diff["changed_files"] == ["docs/api.md"]
    assert "-BillingAPI docs." in diff["diff"]
    assert "+Current BillingAPI documentation." in diff["diff"]


def test_rejects_path_escape(project: Path) -> None:
    with pytest.raises(ValueError, match="пределы"):
        mcp_server.read_files(["../secret.txt"])


def test_checks_invariants_across_project(project: Path) -> None:
    (project / "src" / "bad.py").write_text("value = 1  ", encoding="utf-8")
    result = mcp_server.check_invariants()
    rules = {item["rule"] for item in result["violations"]}
    assert {"trailing-whitespace", "final-newline"} <= rules
