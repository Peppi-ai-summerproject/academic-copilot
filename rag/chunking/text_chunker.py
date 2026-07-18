"""Text chunking service for the RAG knowledge base."""

from collections.abc import Sequence

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class TextChunker:
    """Split loaded documents into smaller chunks while preserving metadata."""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> None:
        """
        Initialize the text chunker.

        Args:
            chunk_size:
                Maximum approximate number of characters in each chunk.

            chunk_overlap:
                Number of characters shared between consecutive chunks.

        Raises:
            ValueError:
                If the chunking configuration is invalid.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")

        if chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative")

        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def split_documents(
        self,
        documents: Sequence[Document],
    ) -> list[Document]:
        """
        Split documents into smaller chunks.

        Original document metadata is preserved. Each generated chunk receives
        additional chunk-specific metadata.

        Args:
            documents:
                Documents produced by the document loader.

        Returns:
            A list of chunked documents.

        Raises:
            ValueError:
                If a document contains empty content.
        """
        if not documents:
            return []

        chunked_documents: list[Document] = []

        for document_index, document in enumerate(documents):
            content = document.page_content.strip()

            if not content:
                raise ValueError(
                    f"Document at index {document_index} contains empty content"
                )

            chunks = self._splitter.split_text(content)

            for chunk_index, chunk_text in enumerate(chunks):
                metadata = {
                    **document.metadata,
                    "document_index": document_index,
                    "chunk_index": chunk_index,
                    "chunk_size": len(chunk_text),
                }

                chunked_documents.append(
                    Document(
                        page_content=chunk_text,
                        metadata=metadata,
                    )
                )

        return chunked_documents