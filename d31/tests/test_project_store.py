from pathlib import Path

import pytest

import project_store


def test_normalize_and_project_id_are_stable() -> None:
    url = "https://github.com/vapechatkin/capitoly.git/"
    normalized = project_store.normalize_repo_url(url)
    assert normalized == "https://github.com/vapechatkin/capitoly.git"
    assert project_store.project_id_for(url) == project_store.project_id_for(normalized)
    assert len(project_store.project_id_for(url)) == 16


@pytest.mark.parametrize("value", ["/tmp/repo", "file:///tmp/repo", "github.com/a/b"])
def test_only_remote_git_urls_are_accepted(value: str) -> None:
    with pytest.raises(ValueError):
        project_store.normalize_repo_url(value)


def test_last_project_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(project_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(project_store, "STATE_FILE", state_file)
    url = "https://github.com/acme/project.git"
    project_id = project_store.project_id_for(url)

    project_store.save_last_project(url, project_id)

    assert project_store.load_last_project() == project_store.LastProject(url, project_id)
