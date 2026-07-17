"""Local stdio MCP server that owns the cached Git repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from project_store import (
    normalize_repo_url,
    project_dir,
    project_id_for,
    repo_dir,
    validate_project_id,
)


mcp = FastMCP(
    "d31 Git Project Server",
    instructions=(
        "Connect a Git repository to the developer assistant and expose its "
        "current branch, commit and file list."
    ),
    json_response=True,
    log_level="ERROR",
)


def _git(arguments: list[str], cwd: Path | None = None, timeout: int = 120) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(message or f"git завершился с кодом {completed.returncode}")
    return completed.stdout.strip()


def _checked_repo(project_id: str) -> Path:
    path = repo_dir(validate_project_id(project_id))
    if not (path / ".git").is_dir():
        raise ValueError("Проект ещё не подключён")
    return path


def _repo_info(path: Path, *, reused: bool, sync_error: str | None = None) -> dict[str, Any]:
    branch = _git(["branch", "--show-current"], cwd=path)
    commit = _git(["rev-parse", "HEAD"], cwd=path)
    origin = _git(["remote", "get-url", "origin"], cwd=path)
    return {
        "repository_path": str(path),
        "repository_url": origin,
        "branch": branch,
        "commit": commit,
        "cache_reused": reused,
        "sync_error": sync_error,
    }


@mcp.tool()
def connect_repository(repo_url: str, project_id: str) -> dict[str, Any]:
    """Clone a repository into the controlled cache or fast-forward its cached copy."""
    validate_project_id(project_id)
    normalized_url = normalize_repo_url(repo_url)
    if project_id_for(normalized_url) != project_id:
        raise ValueError("Git URL не совпадает с идентификатором проекта")
    root = project_dir(project_id)
    path = repo_dir(project_id)
    root.mkdir(parents=True, exist_ok=True)

    if not (path / ".git").is_dir():
        if path.exists() and any(path.iterdir()):
            raise ValueError("Каталог кэша существует, но не является Git-репозиторием")
        path.parent.mkdir(parents=True, exist_ok=True)
        _git(["clone", "--depth", "1", normalized_url, str(path)], timeout=300)
        return _repo_info(path, reused=False)

    cached_origin = _git(["remote", "get-url", "origin"], cwd=path)
    if normalize_repo_url(cached_origin) != normalized_url:
        raise ValueError("Кэш проекта принадлежит другому Git URL")

    sync_error: str | None = None
    try:
        _git(["pull", "--ff-only"], cwd=path, timeout=180)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        # A previously built cache remains useful while the network is unavailable.
        sync_error = str(exc)
    return _repo_info(path, reused=True, sync_error=sync_error)


@mcp.tool()
def git_branch(project_id: str) -> dict[str, str]:
    """Return the current Git branch for a connected project."""
    path = _checked_repo(project_id)
    return {"branch": _git(["branch", "--show-current"], cwd=path)}


@mcp.tool()
def git_commit(project_id: str) -> dict[str, str]:
    """Return the current HEAD commit for a connected project."""
    path = _checked_repo(project_id)
    return {"commit": _git(["rev-parse", "HEAD"], cwd=path)}


@mcp.tool()
def list_files(project_id: str, limit: int = 200) -> dict[str, Any]:
    """Return tracked files from a connected repository."""
    path = _checked_repo(project_id)
    safe_limit = max(1, min(limit, 1000))
    files = _git(["ls-files"], cwd=path).splitlines()
    return {
        "files": files[:safe_limit],
        "total": len(files),
        "truncated": len(files) > safe_limit,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
