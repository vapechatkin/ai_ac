"""BM25 RAG over project documentation and source code for PR review."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Mapping

from github_client import PullRequestContext


MAX_FILE_BYTES = 600_000
CHUNK_CHARS = 2_200
OVERLAP_LINES = 5
DOCUMENT_EXTENSIONS = {".md", ".mdx", ".rst", ".txt", ".html", ".htm"}
DATA_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".graphql", ".proto"}
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".dart",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".swift",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cs",
    ".rb",
    ".php",
    ".scala",
    ".sh",
    ".sql",
}
SPECIAL_CODE_FILES = {"dockerfile", "makefile", "justfile", "procfile"}
IGNORED_PARTS = {
    ".git",
    ".dart_tool",
    ".idea",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "vendor",
    "coverage",
    "generated",
    "Pods",
}
IGNORED_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pubspec.lock",
    "poetry.lock",
    "Cargo.lock",
}
SCHEMA_MARKERS = ("openapi", "swagger", "asyncapi", "schema", "api")

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_./:-]+")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_SYMBOL_RE = re.compile(
    r"^\s*(?:class|def|async\s+def|function|interface|enum|struct|func)\s+([A-Za-z_][\w]*)"
)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "div", "h1", "h2", "h3", "li", "p", "section", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"div", "h1", "h2", "h3", "li", "p", "section", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class SourceFile:
    path: str
    kind: str
    text: str


@dataclass(frozen=True)
class Chunk:
    path: str
    line_start: int
    line_end: int
    heading: str
    kind: str
    text: str

    @property
    def citation(self) -> str:
        return f"{self.path}:{self.line_start}-{self.line_end}"


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float


def classify_path(relative: Path) -> str | None:
    if relative.name in IGNORED_FILENAMES:
        return None
    if any(
        part.startswith(".")
        or part in IGNORED_PARTS
        or part.lower().endswith(".xcassets")
        for part in relative.parts
    ):
        return None
    name = relative.name.lower()
    suffix = relative.suffix.lower()
    in_docs = any(
        part.lower() in {"docs", "doc", "documentation"}
        for part in relative.parts[:-1]
    )
    if name.startswith("readme") or in_docs:
        return "documentation" if suffix in DOCUMENT_EXTENSIONS | DATA_EXTENSIONS else None
    if suffix in DATA_EXTENSIONS and any(marker in relative.stem.lower() for marker in SCHEMA_MARKERS):
        return "documentation"
    if suffix in CODE_EXTENSIONS | DATA_EXTENSIONS or name in SPECIAL_CODE_FILES:
        return "code"
    return None


def discover_project_files(repository: Path) -> list[Path]:
    files: list[Path] = []
    for path in repository.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repository)
        if classify_path(relative) is None:
            continue
        try:
            if path.stat().st_size <= MAX_FILE_BYTES:
                files.append(path)
        except OSError:
            continue
    return sorted(files, key=lambda item: item.as_posix().lower())


def read_source(path: Path, kind: str) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if kind == "documentation" and path.suffix.lower() in {".html", ".htm"}:
        parser = _HTMLTextExtractor()
        parser.feed(raw)
        return parser.text()
    return raw


def chunk_source(source: SourceFile) -> list[Chunk]:
    lines = source.text.splitlines()
    chunks: list[Chunk] = []
    start = 0
    heading = ""
    while start < len(lines):
        end = start
        size = 0
        current_heading = heading
        while end < len(lines):
            heading_match = _HEADING_RE.match(lines[end])
            symbol_match = _SYMBOL_RE.match(lines[end])
            if heading_match:
                current_heading = heading_match.group(1).strip()
            elif symbol_match:
                current_heading = symbol_match.group(1)
            addition = len(lines[end]) + 1
            if end > start and size + addition > CHUNK_CHARS:
                break
            size += addition
            end += 1
        text = "\n".join(lines[start:end]).strip()
        if text:
            chunks.append(
                Chunk(
                    path=source.path,
                    line_start=start + 1,
                    line_end=end,
                    heading=current_heading,
                    kind=source.kind,
                    text=text,
                )
            )
        for line in lines[start:end]:
            match = _HEADING_RE.match(line) or _SYMBOL_RE.match(line)
            if match:
                heading = match.group(1).strip()
        if end >= len(lines):
            break
        start = max(start + 1, end - OVERLAP_LINES)
    return chunks


def tokenize(text: str) -> list[str]:
    output: list[str] = []
    for raw in _WORD_RE.findall(text.lower()):
        for piece in [raw, *re.split(r"[_./:-]+", raw)]:
            if len(piece) < 2:
                continue
            output.append(piece)
            if len(piece) >= 5 and piece.isalpha():
                output.extend(
                    f"§{piece[index:index + 3]}" for index in range(len(piece) - 2)
                )
    return output


class RAGIndex:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.term_frequencies = [dict(Counter(tokenize(chunk.text))) for chunk in chunks]
        self.lengths = [sum(frequencies.values()) for frequencies in self.term_frequencies]
        self.average_length = sum(self.lengths) / max(1, len(self.lengths))
        self.document_frequency: Counter[str] = Counter()
        for frequencies in self.term_frequencies:
            self.document_frequency.update(frequencies.keys())

    @classmethod
    def build(
        cls,
        repository: Path,
        changed_file_contents: Mapping[str, str] | None = None,
    ) -> tuple["RAGIndex", int]:
        sources: dict[str, SourceFile] = {}
        for path in discover_project_files(repository):
            relative = path.relative_to(repository)
            kind = classify_path(relative)
            if kind is None:
                continue
            try:
                text = read_source(path, kind)
            except OSError:
                continue
            sources[relative.as_posix()] = SourceFile(relative.as_posix(), kind, text)

        for raw_path, text in (changed_file_contents or {}).items():
            relative = Path(raw_path)
            kind = classify_path(relative)
            if kind is not None and text.strip():
                sources[relative.as_posix()] = SourceFile(relative.as_posix(), kind, text)

        chunks = [chunk for source in sources.values() for chunk in chunk_source(source)]
        if not chunks:
            raise RuntimeError("Не найдены документация и исходный код для RAG")
        return cls(chunks), len(sources)

    def search(
        self, query: str, top_k: int = 8, kind: str | None = None
    ) -> list[SearchResult]:
        query_terms = Counter(tokenize(query))
        count = len(self.chunks)
        if not query_terms or not count:
            return []
        scored: list[SearchResult] = []
        for index, frequencies in enumerate(self.term_frequencies):
            chunk = self.chunks[index]
            if kind is not None and chunk.kind != kind:
                continue
            score = 0.0
            for term, query_weight in query_terms.items():
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                df = self.document_frequency[term]
                inverse_frequency = math.log(1 + (count - df + 0.5) / (df + 0.5))
                denominator = frequency + 1.5 * (
                    0.25 + 0.75 * self.lengths[index] / max(1.0, self.average_length)
                )
                score += query_weight * inverse_frequency * frequency * 2.5 / denominator
            if score > 0:
                scored.append(SearchResult(chunk, score))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(1, top_k)]

    def balanced_search(self, query: str) -> list[SearchResult]:
        documentation = self.search(query, top_k=4, kind="documentation")
        code = self.search(query, top_k=6, kind="code")
        combined = sorted([*documentation, *code], key=lambda item: item.score, reverse=True)
        return combined[:10]


def build_retrieval_query(pr: PullRequestContext) -> str:
    patches = "\n".join(file.patch[:5_000] for file in pr.files if file.patch)
    return "\n".join(
        [
            pr.title,
            pr.body[:5_000],
            " ".join(pr.changed_paths),
            patches[:30_000],
        ]
    )


def format_rag_context(results: Iterable[SearchResult]) -> str:
    sections: list[str] = []
    for number, result in enumerate(results, start=1):
        chunk = result.chunk
        heading = f" — {chunk.heading}" if chunk.heading else ""
        sections.append(
            f"[RAG {number}: {chunk.citation} · {chunk.kind}{heading}]\n{chunk.text}"
        )
    return "\n\n".join(sections)
