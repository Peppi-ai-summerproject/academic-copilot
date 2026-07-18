# RAG Research

This document contains research notes for the RAG topic and is the repo-friendly Markdown version of the research.

- Original Word file: `research/week1/rag.docx`
- Markdown file for team review: `research/week1/rag.md`

## Goal

Document how Retrieval-Augmented Generation (RAG) works, why it is useful, and how it can be applied in our academic copilot backend.

## What is RAG?

RAG stands for Retrieval-Augmented Generation.

- It combines a retrieval system with a generative model.
- The retrieval system finds relevant documents or knowledge snippets.
- The generative model uses those retrieved documents to produce accurate responses.

## Why use RAG?

- Improves factual accuracy by grounding the model in real content.
- Reduces hallucinations compared to pure generation.
- Allows the model to answer questions from a changing knowledge base without retraining.

## Core components

1. **Retriever**
   - Indexes documents, text, or knowledge sources.
   - Finds the most relevant chunks for a query.
2. **Reader / Generator**
   - Takes retrieved text plus the query.
   - Generates a response that uses the retrieved information.
3. **Vector store or search engine**
   - Stores document embeddings.
   - Supports similarity search for queries.

## How it works

1. User question arrives.
2. Query is converted into an embedding.
3. The embedding is used to search a vector store.
4. Most relevant documents are retrieved.
5. The generative model conditions on the query + retrieved text.
6. The model outputs a grounded answer.

## Use cases for our project

- Answering student questions using course content.
- Summarizing academic documents with context.
- Creating a chat assistant that references stored lecture notes or research notes.

## Open questions / next steps

- Which knowledge sources should we index first?
  - Lecture notes
  - Course materials
  - Meeting notes
- Which embedding model should we use?
- What vector store or search backend is best for our deployment?
- How should we connect RAG output with the existing FastAPI backend?

## Notes

- Keep this file in `research/week1/` alongside the existing `rag.docx`.
- This is a starting point and can be expanded as research progresses.
