"""Unit tests for context injection layer - Issue #62."""

import pytest
from rag.retriever.models import RetrievedChunk
from rag.context.models import InjectedContext
from rag.context.prompt_builder import PromptBuilder
from rag.context.context_injector import ContextInjector
from rag.context.templates import ACADEMIC_TUTOR_TEMPLATE


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_chunk(id="1", text="Study right lasts 7 years.", score=0.9, filename="policy.docx"):
    return RetrievedChunk(id=id, text=text, score=score, metadata={"filename": filename})

def make_injector(max_chunks=5, max_context_length=4000):
    builder = PromptBuilder(include_metadata=True)
    return ContextInjector(prompt_builder=builder, max_chunks=max_chunks, max_context_length=max_context_length)


# ── InjectedContext model tests ───────────────────────────────────────────────

def test_injected_context_valid():
    ctx = InjectedContext(prompt="test prompt", question="test?", chunk_count=2, total_context_length=100)
    assert ctx.prompt == "test prompt"
    assert ctx.chunk_count == 2

def test_injected_context_empty_prompt_raises():
    with pytest.raises(ValueError, match="prompt"):
        InjectedContext(prompt="", question="test?", chunk_count=0, total_context_length=0)

def test_injected_context_empty_question_raises():
    with pytest.raises(ValueError, match="question"):
        InjectedContext(prompt="test", question="", chunk_count=0, total_context_length=0)

def test_injected_context_is_frozen():
    ctx = InjectedContext(prompt="p", question="q", chunk_count=1, total_context_length=10)
    with pytest.raises(Exception):
        ctx.prompt = "changed"


# ── PromptBuilder tests ───────────────────────────────────────────────────────

def test_prompt_builder_contains_question():
    builder = PromptBuilder()
    chunks = [make_chunk()]
    prompt = builder.build_prompt("What is the study right policy?", chunks)
    assert "What is the study right policy?" in prompt

def test_prompt_builder_contains_chunk_text():
    builder = PromptBuilder()
    chunks = [make_chunk(text="Study right lasts 7 years.")]
    prompt = builder.build_prompt("question?", chunks)
    assert "Study right lasts 7 years." in prompt

def test_prompt_builder_contains_metadata():
    builder = PromptBuilder(include_metadata=True)
    chunks = [make_chunk(filename="academic_policy.docx", score=0.95)]
    prompt = builder.build_prompt("question?", chunks)
    assert "academic_policy.docx" in prompt
    assert "0.95" in prompt

def test_prompt_builder_no_metadata():
    builder = PromptBuilder(include_metadata=False)
    chunks = [make_chunk(filename="academic_policy.docx")]
    prompt = builder.build_prompt("question?", chunks)
    assert "academic_policy.docx" not in prompt

def test_prompt_builder_empty_chunks_shows_no_context_message():
    builder = PromptBuilder()
    prompt = builder.build_prompt("question?", [])
    assert "No relevant context" in prompt

def test_prompt_builder_empty_question_raises():
    builder = PromptBuilder()
    with pytest.raises(ValueError, match="empty"):
        builder.build_prompt("", [make_chunk()])

def test_prompt_builder_whitespace_question_raises():
    builder = PromptBuilder()
    with pytest.raises(ValueError, match="empty"):
        builder.build_prompt("   ", [make_chunk()])

def test_prompt_builder_contains_template_instructions():
    builder = PromptBuilder()
    prompt = builder.build_prompt("question?", [make_chunk()])
    assert "do not invent" in prompt.lower() or "not available" in prompt.lower() or "only" in prompt.lower()

def test_prompt_builder_preserves_chunk_order():
    builder = PromptBuilder(include_metadata=False)
    chunks = [
        make_chunk(id="1", text="First chunk content", score=0.95),
        make_chunk(id="2", text="Second chunk content", score=0.80),
        make_chunk(id="3", text="Third chunk content", score=0.70),
    ]
    prompt = builder.build_prompt("question?", chunks)
    pos1 = prompt.index("First chunk content")
    pos2 = prompt.index("Second chunk content")
    pos3 = prompt.index("Third chunk content")
    assert pos1 < pos2 < pos3

def test_prompt_builder_multiple_chunks_separated():
    builder = PromptBuilder(chunk_separator="---")
    chunks = [make_chunk(id="1", text="Chunk A"), make_chunk(id="2", text="Chunk B")]
    prompt = builder.build_prompt("question?", chunks)
    assert "---" in prompt


# ── ContextInjector tests ─────────────────────────────────────────────────────

def test_context_injector_returns_injected_context():
    injector = make_injector()
    chunks = [make_chunk()]
    result = injector.inject_context("What is the study right?", chunks)
    assert isinstance(result, InjectedContext)
    assert result.chunk_count == 1

def test_context_injector_empty_question_raises():
    injector = make_injector()
    with pytest.raises(ValueError, match="empty"):
        injector.inject_context("", [make_chunk()])

def test_context_injector_whitespace_question_raises():
    injector = make_injector()
    with pytest.raises(ValueError, match="empty"):
        injector.inject_context("   ", [make_chunk()])

def test_context_injector_removes_empty_chunks():
    from unittest.mock import MagicMock
    injector = make_injector()
    empty_chunk = MagicMock()
    empty_chunk.text = ""
    empty_chunk.id = "2"
    whitespace_chunk = MagicMock()
    whitespace_chunk.text = "   "
    whitespace_chunk.id = "3"
    valid_chunk = make_chunk(id="1", text="Valid text")
    chunks = [valid_chunk, empty_chunk, whitespace_chunk]
    result = injector.inject_context("question?", chunks)
    assert result.chunk_count == 1

def test_context_injector_removes_duplicate_chunks():
    injector = make_injector()
    chunks = [
        make_chunk(id="1", text="Duplicate content"),
        make_chunk(id="2", text="Duplicate content"),
        make_chunk(id="3", text="Unique content"),
    ]
    result = injector.inject_context("question?", chunks)
    assert result.chunk_count == 2

def test_context_injector_respects_max_chunks():
    injector = make_injector(max_chunks=2)
    chunks = [
        make_chunk(id="1", text="Chunk one"),
        make_chunk(id="2", text="Chunk two"),
        make_chunk(id="3", text="Chunk three"),
    ]
    result = injector.inject_context("question?", chunks)
    assert result.chunk_count == 2

def test_context_injector_respects_max_context_length():
    injector = make_injector(max_context_length=20)
    chunks = [
        make_chunk(id="1", text="Short"),
        make_chunk(id="2", text="Another short chunk that exceeds limit"),
    ]
    result = injector.inject_context("question?", chunks)
    assert result.total_context_length <= 20

def test_context_injector_preserves_ranking_order():
    injector = make_injector()
    chunks = [
        make_chunk(id="1", text="High score chunk", score=0.95),
        make_chunk(id="2", text="Low score chunk", score=0.50),
    ]
    result = injector.inject_context("question?", chunks)
    pos_high = result.prompt.index("High score chunk")
    pos_low = result.prompt.index("Low score chunk")
    assert pos_high < pos_low

def test_context_injector_no_chunks_returns_valid_context():
    injector = make_injector()
    result = injector.inject_context("question?", [])
    assert result.chunk_count == 0
    assert "No relevant context" in result.prompt

def test_context_injector_prompt_contains_question():
    injector = make_injector()
    result = injector.inject_context("What are graduation requirements?", [make_chunk()])
    assert "What are graduation requirements?" in result.prompt


# ── Integration test (no LLM, no Qdrant needed) ───────────────────────────────

def test_integration_full_context_pipeline():
    """Integration test: retriever chunks → context injector → final prompt."""
    import os
    if os.getenv("RUN_RAG_LIVE_INTEGRATION") != "1":
        pytest.skip("Set RUN_RAG_LIVE_INTEGRATION=1 to run live RAG integration tests.")

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not gemini_key:
        pytest.skip("GEMINI_API_KEY not set — skipping integration test")

    try:
        from qdrant_client import QdrantClient
        from rag.embeddings.gemini_embedding_provider import GeminiEmbeddingProvider
        from rag.embeddings.embedding_service import EmbeddingService
        from rag.retriever.qdrant_retriever import QdrantRetriever
        from rag.retriever.retrieval_service import RetrievalService
        from rag.context.prompt_builder import PromptBuilder
        from rag.context.context_injector import ContextInjector

        provider = GeminiEmbeddingProvider(api_key=gemini_key)
        embedding_service = EmbeddingService(provider=provider)
        qdrant_client = QdrantClient(url=qdrant_url)
        retriever = QdrantRetriever(
            embedding_service=embedding_service,
            qdrant_client=qdrant_client,
            collection_name="academic_knowledge",
        )
        retrieval_service = RetrievalService(retriever=retriever)

        builder = PromptBuilder(include_metadata=True)
        injector = ContextInjector(prompt_builder=builder, max_chunks=3)

        question = "What is the study right policy?"
        chunks = retrieval_service.retrieve(question, top_k=3)
        result = injector.inject_context(question, chunks)

        print(f"\nIntegration test results:")
        print(f"  Chunks injected: {result.chunk_count}")
        print(f"  Context length: {result.total_context_length}")
        print(f"  Prompt length: {len(result.prompt)}")
        print(f"  Prompt preview:\n{result.prompt[:300]}...")

        assert question in result.prompt
        assert result.chunk_count > 0
        assert len(result.prompt) > 100

    except RuntimeError as e:
        pytest.skip(f"Backend not available: {e}")
