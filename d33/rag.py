"""Small BM25 knowledge-base RAG for support answers."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CHUNK_CHARS = 1_600
OVERLAP_LINES = 3
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_./:-]+")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")


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


def chunk_document(text: str, path: str) -> list[Chunk]:
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
            chunks.append(Chunk(path, start + 1, end, current_heading, body))
        for line in lines[start:end]:
            match = _HEADING_RE.match(line)
            if match:
                heading = match.group(1).strip()
        if end >= len(lines):
            break
        start = max(start + 1, end - OVERLAP_LINES)
    return chunks


class KnowledgeRAG:
    def __init__(self, chunks: list[Chunk]) -> None:
        if not chunks:
            raise ValueError("База знаний пуста")
        self.chunks = chunks
        self.term_frequencies = [dict(Counter(tokenize(chunk.text))) for chunk in chunks]
        self.lengths = [sum(frequencies.values()) for frequencies in self.term_frequencies]
        self.average_length = sum(self.lengths) / len(self.lengths)
        self.document_frequency: Counter[str] = Counter()
        for frequencies in self.term_frequencies:
            self.document_frequency.update(frequencies.keys())

    @classmethod
    def from_directory(cls, directory: Path) -> "KnowledgeRAG":
        chunks: list[Chunk] = []
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".rst"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            chunks.extend(chunk_document(text, path.relative_to(directory).as_posix()))
        return cls(chunks)

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        query_terms = Counter(tokenize(query))
        count = len(self.chunks)
        scored: list[SearchResult] = []
        for index, frequencies in enumerate(self.term_frequencies):
            score = 0.0
            for term, query_weight in query_terms.items():
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                df = self.document_frequency[term]
                inverse_frequency = math.log(1 + (count - df + 0.5) / (df + 0.5))
                denominator = frequency + 1.5 * (
                    0.25 + 0.75 * self.lengths[index] / self.average_length
                )
                score += query_weight * inverse_frequency * frequency * 2.5 / denominator
            if score > 0:
                scored.append(SearchResult(self.chunks[index], score))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(1, top_k)]


def format_context(results: Iterable[SearchResult]) -> str:
    sections: list[str] = []
    for number, result in enumerate(results, start=1):
        heading = f" — {result.chunk.heading}" if result.chunk.heading else ""
        sections.append(
            f"[Источник {number}: {result.chunk.citation}{heading}]\n{result.chunk.text}"
        )
    return "\n\n".join(sections)
