# RAG backend integration

`RagIntegrationService` is the backend application boundary for explicit,
query-time retrieval-augmented generation.

The dependency flow is:

```text
Backend consumer -> RagIntegrationService -> RetrievalService -> Retriever
                                  |
                                  +-> ContextInjector -> PromptBuilder
```

The service accepts a non-empty query and optional `top_k`, preserves the
retriever's result order and metadata, then passes the retrieved chunks to the
existing context injector. It returns a structured `RagIntegrationResult`.

Empty retrieval is a successful result with a warning and a valid no-context
prompt. Retrieval and context-assembly failures return stable error codes and
do not expose infrastructure details.

The integration is intentionally not enabled automatically. API routes, the
Chat Service, agent workflow, Telegram handlers, Qdrant construction, and LLM
answer generation remain outside this issue. A consumer must explicitly call
the service and provide its configured dependencies.

Metadata filtering is also not exposed because the current `Retriever`
protocol supports only `query` and `top_k`. It can be added when that canonical
contract supports filters.
