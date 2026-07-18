"""MCP server for safe, reproducible work with files inside one project."""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


ROOT = Path(os.environ.get("D34_PROJECT_ROOT", ".")).resolve()
MAX_FILE_SIZE = 1_000_000
IGNORED_PARTS = {".git", ".venv", "__pycache__", "node_modules", "dist", "build"}
TEXT_SUFFIXES = {
    ".c", ".cpp", ".css", ".go", ".h", ".html", ".java", ".js", ".json",
    ".jsx", ".kt", ".md", ".py", ".rb", ".rs", ".rst", ".sh", ".sql",
    ".swift", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}

mcp = FastMCP(
    "d34 Project Files",
    instructions="Read, search, validate and update files inside the configured project root.",
    json_response=True,
    log_level="ERROR",
)

# Original contents are kept for a session-level diff, including newly created files.
_originals: dict[str, str | None] = {}


def _path(relative_path: str, *, must_exist: bool = True) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError("Ожидался относительный путь внутри проекта")
    candidate = (ROOT / relative_path).resolve()
    if candidate != ROOT and ROOT not in candidate.parents:
        raise ValueError("Путь выходит за пределы проекта")
    if any(part in IGNORED_PARTS for part in candidate.relative_to(ROOT).parts):
        raise ValueError("Служебный каталог недоступен")
    if must_exist and not candidate.is_file():
        raise ValueError(f"Файл не найден: {relative_path}")
    return candidate


def _files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and not path.name.lower().startswith("readme"):
            continue
        try:
            if path.stat().st_size <= MAX_FILE_SIZE:
                result.append(path)
        except OSError:
            continue
    return sorted(result, key=lambda item: item.relative_to(ROOT).as_posix())


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Файл не является UTF-8 текстом: {path.name}") from exc


def _matches(path: Path, pattern: str) -> bool:
    """Match useful project globs; ``**/*`` includes root-level files too."""
    normalized = pattern.strip() or "**/*"
    return normalized in {"*", "**", "**/*"} or path.match(normalized)


@mcp.tool()
def list_files(glob: str = "**/*", limit: int = 500) -> dict[str, Any]:
    """List text/source files. Use this first to understand project structure."""
    safe_limit = max(1, min(limit, 1000))
    pattern = glob.strip() or "**/*"
    files = [p.relative_to(ROOT).as_posix() for p in _files() if _matches(p.relative_to(ROOT), pattern)]
    return {"files": files[:safe_limit], "total": len(files), "truncated": len(files) > safe_limit}


@mcp.tool()
def search_text(query: str, glob: str = "**/*", max_results: int = 100) -> dict[str, Any]:
    """Search a literal string across project files and return matching lines."""
    if not query:
        raise ValueError("Строка поиска не может быть пустой")
    safe_limit = max(1, min(max_results, 500))
    matches: list[dict[str, Any]] = []
    scanned = 0
    for path in _files():
        relative = path.relative_to(ROOT)
        if not _matches(relative, glob):
            continue
        scanned += 1
        for line_number, line in enumerate(_read(path).splitlines(), 1):
            if query.casefold() in line.casefold():
                matches.append({"path": relative.as_posix(), "line": line_number, "text": line[:500]})
                if len(matches) >= safe_limit:
                    return {"query": query, "matches": matches, "scanned_files": scanned, "truncated": True}
    return {"query": query, "matches": matches, "scanned_files": scanned, "truncated": False}


@mcp.tool()
def read_files(paths: list[str], start_line: int = 1, end_line: int = 400) -> dict[str, Any]:
    """Read one or several project files with line numbers (at most 10 per call)."""
    if not paths or len(paths) > 10:
        raise ValueError("Передайте от 1 до 10 файлов")
    start = max(1, start_line)
    end = min(max(start, end_line), start + 999)
    result: list[dict[str, Any]] = []
    for relative in paths:
        lines = _read(_path(relative)).splitlines()
        content = "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, min(end, len(lines)) + 1))
        result.append({"path": relative, "content": content, "total_lines": len(lines)})
    return {"files": result}


@mcp.tool()
def write_file(path: str, content: str) -> dict[str, Any]:
    """Create or replace a UTF-8 text file atomically. Send the complete new content."""
    target = _path(path, must_exist=False)
    if len(content.encode("utf-8")) > MAX_FILE_SIZE:
        raise ValueError("Файл превышает лимит 1 МБ")
    relative = target.relative_to(ROOT).as_posix()
    current = _read(target) if target.is_file() else None
    if current == content:
        return {"path": relative, "changed": False, "status": "already up to date"}
    _originals.setdefault(relative, current)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".d34.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(target)
    return {"path": relative, "changed": True, "bytes": len(content.encode("utf-8"))}


@mcp.tool()
def check_invariants(glob: str = "**/*") -> dict[str, Any]:
    """Check text files for trailing whitespace, tabs, missing final newline and duplicate Markdown headings."""
    violations: list[dict[str, Any]] = []
    checked = 0
    for path in _files():
        relative = path.relative_to(ROOT)
        if not _matches(relative, glob):
            continue
        checked += 1
        text = _read(path)
        for number, line in enumerate(text.splitlines(), 1):
            if line != line.rstrip():
                violations.append({"path": relative.as_posix(), "line": number, "rule": "trailing-whitespace"})
            if "\t" in line and path.suffix.lower() in {".py", ".md", ".json", ".yaml", ".yml"}:
                violations.append({"path": relative.as_posix(), "line": number, "rule": "tab-character"})
        if text and not text.endswith("\n"):
            violations.append({"path": relative.as_posix(), "line": len(text.splitlines()), "rule": "final-newline"})
        if path.suffix.lower() == ".md":
            headings: dict[str, int] = {}
            for number, line in enumerate(text.splitlines(), 1):
                match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
                if match:
                    heading = match.group(1).casefold()
                    if heading in headings:
                        violations.append({"path": relative.as_posix(), "line": number, "rule": "duplicate-heading"})
                    headings[heading] = number
    return {"checked_files": checked, "violations": violations, "ok": not violations}


@mcp.tool()
def diff_changes() -> dict[str, Any]:
    """Return a unified diff of every file changed by write_file in this session."""
    chunks: list[str] = []
    changed: list[str] = []
    for relative, before in sorted(_originals.items()):
        target = _path(relative, must_exist=False)
        after = _read(target) if target.is_file() else None
        if before == after:
            continue
        changed.append(relative)
        chunks.extend(difflib.unified_diff(
            (before or "").splitlines(keepends=True),
            (after or "").splitlines(keepends=True),
            fromfile=f"a/{relative}" if before is not None else "/dev/null",
            tofile=f"b/{relative}" if after is not None else "/dev/null",
        ))
    return {"changed_files": changed, "diff": "".join(chunks), "count": len(changed)}


if __name__ == "__main__":
    if not ROOT.is_dir():
        raise SystemExit(f"Project root does not exist: {ROOT}")
    mcp.run(transport="stdio")
