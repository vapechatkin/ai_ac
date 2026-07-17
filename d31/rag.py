"""Persistent lexical RAG index optimized for documentation and source identifiers."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


INDEX_VERSION = 2
MAX_FILE_BYTES = 1_000_000
CHUNK_CHARS = 1_800
OVERLAP_LINES = 4
SUPPORTED_EXTENSIONS = {
    ".md",
    ".mdx",
    ".rst",
    ".txt",
    ".html",
    ".htm",
    ".yaml",
    ".yml",
    ".json",
}
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
}
SCHEMA_MARKERS = ("openapi", "swagger", "asyncapi", "schema", "api")

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_./:-]+")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")


class _HTMLTextExtractor(HTMLParser):
    _BLOCKS = {
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "table",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class Chunk:
    path: str
    line_start: int
    line_end: int
    heading: str
    text: str

    @property
    def citation(self) -> str:
        return f"{self.path}:{self.line_start}-{self.line_end}"


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class IndexStatus:
    reused: bool
    files: int
    chunks: int
    commit: str


def _is_documentation_file(relative: Path) -> bool:
    if any(
        part.startswith(".")
        or part in IGNORED_PARTS
        or part.lower().endswith(".xcassets")
        for part in relative.parts
    ):
        return False
    suffix = relative.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return False
    name = relative.name.lower()
    if name.startswith("readme"):
        return True
    if any(part.lower() in {"docs", "doc", "documentation"} for part in relative.parts[:-1]):
        return True
    stem = relative.stem.lower()
    return any(marker in stem for marker in SCHEMA_MARKERS)


def discover_documents(repository: Path) -> list[Path]:
    documents: list[Path] = []
    for path in repository.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repository)
        if not _is_documentation_file(relative):
            continue
        try:
            if path.stat().st_size <= MAX_FILE_BYTES:
                documents.append(path)
        except OSError:
            continue
    return sorted(documents, key=lambda path: path.as_posix().lower())


def _read_document(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".html", ".htm"}:
        parser = _HTMLTextExtractor()
        parser.feed(raw)
        return parser.text()
    return raw


def chunk_text(text: str, relative_path: str) -> list[Chunk]:
    lines = text.splitlines()
    chunks: list[Chunk] = []
    start = 0
    heading = ""

    while start < len(lines):
        end = start
        size = 0
        current_heading = heading
        while end < len(lines):
            match = _HEADING_RE.match(lines[end])
            if match:
                current_heading = match.group(1).strip()
            addition = len(lines[end]) + 1
            if end > start and size + addition > CHUNK_CHARS:
                break
            size += addition
            end += 1

        body = "\n".join(lines[start:end]).strip()
        if body:
            chunks.append(
                Chunk(
                    path=relative_path,
                    line_start=start + 1,
                    line_end=end,
                    heading=current_heading,
                    text=body,
                )
            )

        for line in lines[start:end]:
            match = _HEADING_RE.match(line)
            if match:
                heading = match.group(1).strip()
        if end >= len(lines):
            break
        start = max(start + 1, end - OVERLAP_LINES)
    return chunks


def tokenize(text: str) -> list[str]:
    """Word and character tokens support Russian morphology and code identifiers."""
    output: list[str] = []
    for raw in _WORD_RE.findall(text.lower()):
        pieces = [raw, *re.split(r"[_./:-]+", raw)]
        for piece in pieces:
            if len(piece) < 2:
                continue
            output.append(piece)
            if len(piece) >= 5 and piece.isalpha():
                output.extend(f"§{piece[index:index + 3]}" for index in range(len(piece) - 2))
    return output


class RAGIndex:
    def __init__(self, chunks: list[Chunk], term_frequencies: list[dict[str, int]]) -> None:
        if len(chunks) != len(term_frequencies):
            raise ValueError("Повреждённый RAG-индекс")
        self.chunks = chunks
        self.term_frequencies = term_frequencies
        self.lengths = [sum(frequencies.values()) for frequencies in term_frequencies]
        self.average_length = sum(self.lengths) / max(1, len(self.lengths))
        self.document_frequency: Counter[str] = Counter()
        for frequencies in term_frequencies:
            self.document_frequency.update(frequencies.keys())

    @classmethod
    def build(cls, repository: Path) -> tuple["RAGIndex", list[str]]:
        documents = discover_documents(repository)
        chunks: list[Chunk] = []
        indexed_files: list[str] = []
        for path in documents:
            relative = path.relative_to(repository).as_posix()
            try:
                text = _read_document(path)
            except OSError:
                continue
            file_chunks = chunk_text(text, relative)
            if file_chunks:
                indexed_files.append(relative)
                chunks.extend(file_chunks)
        if not chunks:
            raise RuntimeError("В репозитории не найдены README, docs или API-схемы")
        frequencies = [dict(Counter(tokenize(chunk.text))) for chunk in chunks]
        return cls(chunks, frequencies), indexed_files

    def search(self, query: str, top_k: int = 6) -> list[SearchResult]:
        query_terms = Counter(tokenize(query))
        if not query_terms or not self.chunks:
            return []
        count = len(self.chunks)
        k1 = 1.5
        b = 0.75
        scored: list[SearchResult] = []
        for index, frequencies in enumerate(self.term_frequencies):
            score = 0.0
            length = self.lengths[index]
            for term, query_weight in query_terms.items():
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                df = self.document_frequency[term]
                inverse_frequency = math.log(1 + (count - df + 0.5) / (df + 0.5))
                denominator = frequency + k1 * (
                    1 - b + b * length / max(1.0, self.average_length)
                )
                score += query_weight * inverse_frequency * frequency * (k1 + 1) / denominator
            if score > 0:
                scored.append(SearchResult(chunk=self.chunks[index], score=score))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(1, top_k)]

    def to_dict(self) -> dict[str, object]:
        return {
            "version": INDEX_VERSION,
            "chunks": [asdict(chunk) for chunk in self.chunks],
            "term_frequencies": self.term_frequencies,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "RAGIndex":
        if raw.get("version") != INDEX_VERSION:
            raise ValueError("Версия RAG-индекса устарела")
        chunks_raw = raw.get("chunks")
        frequencies_raw = raw.get("term_frequencies")
        if not isinstance(chunks_raw, list) or not isinstance(frequencies_raw, list):
            raise ValueError("Повреждённый RAG-индекс")
        chunks = [Chunk(**item) for item in chunks_raw if isinstance(item, dict)]
        frequencies = [
            {str(key): int(value) for key, value in item.items()}
            for item in frequencies_raw
            if isinstance(item, dict)
        ]
        return cls(chunks, frequencies)


class PersistentRAG:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.index_file = directory / "index.json"
        self.metadata_file = directory / "metadata.json"
        self.index: RAGIndex | None = None
        self.metadata: dict[str, object] = {}

    def ensure(self, repository: Path, commit: str) -> IndexStatus:
        if self.index_file.exists() and self.metadata_file.exists():
            try:
                metadata = json.loads(self.metadata_file.read_text(encoding="utf-8"))
                if (
                    metadata.get("commit") == commit
                    and metadata.get("index_version") == INDEX_VERSION
                ):
                    raw_index = json.loads(self.index_file.read_text(encoding="utf-8"))
                    self.index = RAGIndex.from_dict(raw_index)
                    self.metadata = metadata
                    return IndexStatus(
                        reused=True,
                        files=int(metadata["files"]),
                        chunks=len(self.index.chunks),
                        commit=commit,
                    )
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                pass

        index, indexed_files = RAGIndex.build(repository)
        self.directory.mkdir(parents=True, exist_ok=True)
        metadata = {
            "index_version": INDEX_VERSION,
            "commit": commit,
            "files": len(indexed_files),
            "chunks": len(index.chunks),
            "indexed_files": indexed_files,
        }
        _write_json_atomic(self.index_file, index.to_dict())
        _write_json_atomic(self.metadata_file, metadata)
        self.index = index
        self.metadata = metadata
        return IndexStatus(
            reused=False,
            files=len(indexed_files),
            chunks=len(index.chunks),
            commit=commit,
        )

    def search(self, query: str, top_k: int = 6) -> list[SearchResult]:
        if self.index is None:
            raise RuntimeError("RAG-индекс не загружен")
        return self.index.search(query, top_k=top_k)


def _write_json_atomic(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def format_context(results: Iterable[SearchResult]) -> str:
    sections: list[str] = []
    for number, result in enumerate(results, start=1):
        chunk = result.chunk
        title = f" — {chunk.heading}" if chunk.heading else ""
        sections.append(
            f"[Источник {number}: {chunk.citation}{title}]\n{chunk.text}"
        )
    return "\n\n".join(sections)
