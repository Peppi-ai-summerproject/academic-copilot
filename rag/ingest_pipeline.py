"""RAG Ingest Pipeline - Load documents into Qdrant"""

import os
import sys
import uuid
sys.path.insert(0, '/opt/academic-copilot/academic-copilot/rag')

from document_loader import DocumentLoader
from chunking.text_chunker import TextChunker
from embeddings.embedding_service import EmbeddingService
from embeddings.gemini_embedding_provider import GeminiEmbeddingProvider
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
KNOWLEDGE_BASE_DIR = "/opt/academic-copilot/academic-copilot/docs/knowledge_base"
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "academic_knowledge"

def main():
    print("Step 1: Loading documents...")
    loader = DocumentLoader()
    docs = loader.load_directory(KNOWLEDGE_BASE_DIR)

    print("Step 2: Chunking documents...")
    chunker = TextChunker(chunk_size=800, chunk_overlap=100)
    chunks = chunker.split_documents(docs)
    print(f"Created {len(chunks)} chunks")

    print("Step 3: Creating Gemini embeddings...")
    provider = GeminiEmbeddingProvider(api_key=GEMINI_API_KEY)
    service = EmbeddingService(provider=provider)
    embedded = service.embed_chunks(chunks)
    print(f"Created {len(embedded)} embeddings")

    print("Step 4: Storing in Qdrant...")
    qdrant = QdrantClient(url=QDRANT_URL)
    points = []
    for item in embedded:
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=item.vector,
            payload=item.payload,
        ))

    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    count = qdrant.count(collection_name=COLLECTION_NAME)
    print(f"Done! Total vectors in Qdrant: {count.count}")

if __name__ == "__main__":
    main()
