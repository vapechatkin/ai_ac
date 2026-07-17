"""Persistent project identity and cache layout for d31."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
STATE_FILE = DATA_DIR / "state.json"

_PROJECT_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def normalize_repo_url(repo_url: str) -> str:
    """Validate and normalize an HTTPS or SSH Git repository URL."""
    value = repo_url.strip().rstrip("/")
    if value.startswith("git@"):
        if ":" not in value or value.endswith(":"):
            raise ValueError("Некорректный SSH Git URL")
    else:
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"https", "ssh"}
            or not parsed.netloc
            or not parsed.path.strip("/")
        ):
            raise ValueError(
                "Ожидался Git URL вида https://host/user/repo.git "
                "или git@host:user/repo.git"
            )
    return value


def project_id_for(repo_url: str) -> str:
    normalized = normalize_repo_url(repo_url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def validate_project_id(project_id: str) -> str:
    if not _PROJECT_ID_RE.fullmatch(project_id):
        raise ValueError("Некорректный идентификатор проекта")
    return project_id


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / validate_project_id(project_id)


def repo_dir(project_id: str) -> Path:
    return project_dir(project_id) / "repository"


def rag_dir(project_id: str) -> Path:
    return project_dir(project_id) / "rag"


@dataclass(frozen=True)
class LastProject:
    repo_url: str
    project_id: str


def load_last_project() -> LastProject | None:
    if not STATE_FILE.exists():
        return None
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        repo_url = normalize_repo_url(str(raw["repo_url"]))
        project_id = validate_project_id(str(raw["project_id"]))
        if project_id != project_id_for(repo_url):
            return None
        return LastProject(repo_url=repo_url, project_id=project_id)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def save_last_project(repo_url: str, project_id: str) -> None:
    normalized = normalize_repo_url(repo_url)
    validated_id = validate_project_id(project_id)
    if validated_id != project_id_for(normalized):
        raise ValueError("URL и идентификатор проекта не совпадают")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"repo_url": normalized, "project_id": validated_id}
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(STATE_FILE)
