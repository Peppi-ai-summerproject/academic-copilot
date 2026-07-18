from google import genai
from google.genai import types


class GeminiEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-001",
        vector_size: int = 768,
    ) -> None:
        if not api_key:
            raise ValueError("Gemini API key must not be empty.")

        if vector_size <= 0:
            raise ValueError("Vector size must be greater than zero.")

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._vector_size = vector_size

    @property
    def vector_size(self) -> int:
        return self._vector_size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self._client.models.embed_content(
            model=self._model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self._vector_size,
            ),
        )

        if not response.embeddings:
            raise RuntimeError("Gemini returned no embeddings.")

        return [embedding.values for embedding in response.embeddings]