import os

import pytest
from dotenv import load_dotenv

from rag.embeddings import GeminiEmbeddingProvider


load_dotenv("backend/.env")


@pytest.mark.integration
def test_gemini_returns_real_embedding() -> None:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        pytest.skip("GEMINI_API_KEY is not configured.")

    provider = GeminiEmbeddingProvider(
        api_key=api_key,
        vector_size=768,
    )

    vectors = provider.embed_documents(
        ["Academic tutoring helps students complete their studies."]
    )

    assert len(vectors) == 1
    assert len(vectors[0]) == 768
    assert all(isinstance(value, float) for value in vectors[0])