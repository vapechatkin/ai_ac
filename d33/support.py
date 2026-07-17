"""Orchestration: MCP CRM context -> RAG -> Claude support answer."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from crm_mcp_client import CRMContext
from rag import KnowledgeRAG, format_context


class CRMResolver(Protocol):
    async def resolve_context(
        self, ticket_id: str | None = None, user_id: str | None = None
    ) -> CRMContext: ...


class SupportLLM(Protocol):
    model: str

    def answer(
        self, question: str, crm_context: CRMContext, knowledge_context: str
    ) -> str: ...


@dataclass(frozen=True)
class SupportResult:
    answer: str
    sources: tuple[str, ...]
    ticket_id: str | None
    user_id: str | None
    model: str


class SupportEngine:
    def __init__(self, rag: KnowledgeRAG, crm: CRMResolver, llm: SupportLLM) -> None:
        self.rag = rag
        self.crm = crm
        self.llm = llm

    async def answer(
        self,
        question: str,
        ticket_id: str | None = None,
        user_id: str | None = None,
    ) -> SupportResult:
        crm_context = await self.crm.resolve_context(ticket_id, user_id)
        query = _build_query(question, crm_context)
        results = self.rag.search(query, top_k=5)
        knowledge = format_context(results)
        response = await asyncio.to_thread(
            self.llm.answer, question, crm_context, knowledge
        )
        sources = tuple(dict.fromkeys(result.chunk.citation for result in results))
        return SupportResult(
            answer=response,
            sources=sources,
            ticket_id=crm_context.ticket_id,
            user_id=crm_context.user_id,
            model=self.llm.model,
        )


def _build_query(question: str, context: CRMContext) -> str:
    parts = [question]
    if context.ticket:
        parts.extend(
            str(context.ticket.get(key, ""))
            for key in ("subject", "description", "error_code", "tags")
        )
    if context.user:
        parts.extend(
            str(context.user.get(key, ""))
            for key in ("platform", "app_version", "account_status", "plan")
        )
    return "\n".join(parts)
