from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from claude_client import ClaudeSupportClient
from crm_mcp_client import CRMClient
from rag import KnowledgeRAG
from support import SupportEngine, SupportResult


BASE_DIR = Path(__file__).resolve().parent


class SupportRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)
    ticket_id: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)


class SupportResponse(BaseModel):
    answer: str
    sources: list[str]
    ticket_id: str | None
    user_id: str | None
    model: str


def create_app(engine: SupportEngine | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if engine is not None:
            app.state.support_engine = engine
            yield
            return

        rag = KnowledgeRAG.from_directory(BASE_DIR / "knowledge")
        crm = CRMClient()
        async with crm:
            app.state.support_engine = SupportEngine(
                crm=crm,
                rag=rag,
                llm=ClaudeSupportClient(),
            )
            yield

    app = FastAPI(
        title="Capitoly AI Support",
        description="Support assistant with documentation RAG and CRM context via MCP.",
        version="1.0.0",
        lifespan=lifespan,
    )

    def get_engine(request: Request) -> SupportEngine:
        return request.app.state.support_engine

    @app.get("/")
    async def root() -> dict[str, object]:
        return {
            "service": "Capitoly AI Support",
            "endpoints": {"health": "GET /health", "support": "POST /support"},
        }

    @app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        current_engine = get_engine(request)
        return {
            "status": "ok",
            "rag_chunks": len(current_engine.rag.chunks),
            "crm_transport": "MCP stdio",
        }

    @app.post("/support", response_model=SupportResponse)
    async def support(payload: SupportRequest, request: Request) -> SupportResponse:
        try:
            result: SupportResult = await get_engine(request).answer(
                question=payload.question,
                ticket_id=payload.ticket_id,
                user_id=payload.user_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return SupportResponse(
            answer=result.answer,
            sources=result.sources,
            ticket_id=result.ticket_id,
            user_id=result.user_id,
            model=result.model,
        )

    return app


app = create_app()
