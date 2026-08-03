"""RAG Ingest Pipeline - Load documents into Qdrant"""

import sys
import uuid
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from rag.document_loader import DocumentLoader
from rag.chunking.text_chunker import TextChunker
from rag.embeddings.embedding_service import EmbeddingService
from rag.embeddings.gemini_embedding_provider import GeminiEmbeddingProvider
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

def main():
    print("Step 1: Loading documents...")
    loader = DocumentLoader()
    docs = loader.load_directory(settings.knowledge_base_dir)

    print("Step 2: Chunking documents...")
    chunker = TextChunker(chunk_size=800, chunk_overlap=100)
    chunks = chunker.split_documents(docs)
    print(f"Created {len(chunks)} chunks")

    print("Step 3: Creating Gemini embeddings...")
    provider = GeminiEmbeddingProvider(api_key=settings.gemini_api_key)
    service = EmbeddingService(provider=provider)
    embedded = service.embed_chunks(chunks)
    print(f"Created {len(embedded)} embeddings")

    print("Step 4: Storing in Qdrant...")
    qdrant = QdrantClient(url=settings.qdrant_url)
    points = []
    for item in embedded:
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=item.vector,
            payload=item.payload,
        ))

    qdrant.upsert(collection_name=settings.qdrant_collection_name, points=points)
    count = qdrant.count(collection_name=settings.qdrant_collection_name)
    print(f"Done! Total vectors in Qdrant: {count.count}")

if __name__ == "__main__":
    main()
