from __future__ import annotations

import asyncio
from unittest.mock import Mock

from app.gateways.policy_context import RagPolicyContextGateway
from app.services.rag_integration_service import RagIntegrationResult, RagSource
from rag.context.models import InjectedContext
from rag.retriever.models import RetrievedChunk


def test_rag_gateway_preserves_chunk_evidence_and_ignores_prompt_as_evidence():
    chunk = RetrievedChunk(
        id="policy-7",
        text="Tutors should review the study plan.",
        score=0.91,
        metadata={"source": "Academic Policy", "section": "Progress"},
    )
    service = Mock()
    service.execute.return_value = RagIntegrationResult(
        query="academic progress deficit tutor support policy",
        injected_context=InjectedContext("SECRET PROMPT", "question", 1, 10),
        chunks=(chunk,),
        sources=(RagSource("policy-7", 0.91, dict(chunk.metadata)),),
        retrieved_count=1,
    )

    result = asyncio.run(
        RagPolicyContextGateway(service).retrieve_policy("question", top_k=3)
    )

    assert result.succeeded
    assert result.candidates[0].chunk_id == "policy-7"
    assert result.candidates[0].text == chunk.text
    assert result.candidates[0].source == "Academic Policy"
    assert "SECRET PROMPT" not in repr(result)
    service.execute.assert_called_once_with("question", top_k=3)


def test_rag_gateway_returns_controlled_failure():
    service = Mock()
    service.execute.return_value = RagIntegrationResult(
        query="question",
        injected_context=None,
        chunks=(),
        sources=(),
        retrieved_count=0,
        error_code="RAG_RETRIEVAL_UNAVAILABLE",
    )

    result = asyncio.run(RagPolicyContextGateway(service).retrieve_policy("question"))

    assert not result.succeeded
    assert result.error_code == "RAG_RETRIEVAL_UNAVAILABLE"
