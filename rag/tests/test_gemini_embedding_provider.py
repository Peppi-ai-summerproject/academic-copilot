from types import SimpleNamespace

import pytest

from rag.embeddings.gemini_embedding_provider import GeminiEmbeddingProvider


class FakeModels:
    def embed_content(self, **kwargs):
        return SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=[0.1, 0.2, 0.3]),
                SimpleNamespace(values=[0.4, 0.5, 0.6]),
            ]
        )


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


def test_embed_documents_returns_vectors() -> None:
    provider = GeminiEmbeddingProvider(
        api_key="fake-key",
        vector_size=3,
    )
    provider._client = FakeClient()

    result = provider.embed_documents(["first", "second"])

    assert result == [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]


def test_embed_documents_returns_empty_list_for_empty_input() -> None:
    provider = GeminiEmbeddingProvider(
        api_key="fake-key",
        vector_size=3,
    )

    result = provider.embed_documents([])

    assert result == []


def test_provider_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        GeminiEmbeddingProvider(api_key="")


def test_provider_rejects_invalid_vector_size() -> None:
    with pytest.raises(ValueError, match="Vector size"):
        GeminiEmbeddingProvider(
            api_key="fake-key",
            vector_size=0,
        )


class EmptyModels:
    def embed_content(self, **kwargs):
        return SimpleNamespace(embeddings=[])


class EmptyClient:
    def __init__(self):
        self.models = EmptyModels()


def test_provider_raises_error_when_gemini_returns_no_embeddings() -> None:
    provider = GeminiEmbeddingProvider(
        api_key="fake-key",
        vector_size=3,
    )
    provider._client = EmptyClient()

    with pytest.raises(RuntimeError, match="no embeddings"):
        provider.embed_documents(["test"])