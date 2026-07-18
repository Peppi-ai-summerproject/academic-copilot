from langchain_core.documents import Document

from rag.embeddings.base_embedding_provider import EmbeddingProvider
from rag.embeddings.models import EmbeddedChunk


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    def embed_chunks(self, chunks: list[Document]) -> list[EmbeddedChunk]:
        if not chunks:
            return []

        texts = [chunk.page_content for chunk in chunks]

        vectors = self.provider.embed_documents(texts)

        if len(vectors) != len(chunks):
            raise ValueError(
                "Embedding provider returned a different number of vectors "
                "than the number of input chunks."
            )

        embedded_chunks: list[EmbeddedChunk] = []

        for chunk, vector in zip(chunks, vectors):
            if len(vector) != self.provider.vector_size:
                raise ValueError(
                    f"Invalid vector size. Expected "
                    f"{self.provider.vector_size}, got {len(vector)}."
                )

            chunk_id = self._build_chunk_id(chunk)

            payload = {
                "text": chunk.page_content,
                **chunk.metadata,
            }

            embedded_chunks.append(
                EmbeddedChunk(
                    id=chunk_id,
                    vector=vector,
                    payload=payload,
                )
            )

        return embedded_chunks

    @staticmethod
    def _build_chunk_id(chunk: Document) -> str:
        source = str(chunk.metadata.get("source", "unknown"))
        document_index = str(chunk.metadata.get("document_index", 0))
        chunk_index = str(chunk.metadata.get("chunk_index", 0))

        return f"{source}:{document_index}:{chunk_index}"