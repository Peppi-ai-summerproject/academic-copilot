# Agent memory

## Purpose and ownership

Agent memory is bounded conversation context retained across separate trusted
Telegram interactions. `ChatService` owns its complete lifecycle: it resolves
the authorized scope, loads a safe snapshot into `AgentState`, runs the existing
workflow, and saves an approved turn after a safe response is produced.
Individual agents never access SQLAlchemy, repositories, Telegram mappings, or
the memory store.

`AgentState` remains transient state for one workflow invocation. Conversation
memory is not a LangGraph checkpoint: it does not resume nodes or persist
routing/control fields. No checkpointer is configured. Memory is also distinct
from RAG, which retrieves external academic knowledge rather than conversation
turns.

## Identity and isolation

Persistent memory is enabled only for requests authenticated with the internal
Telegram adapter service key. Its scope is the combination of:

- server-resolved conversation UUID;
- owner type `telegram`;
- normalized owner reference containing the trusted Telegram user and chat;
- exact student ID partition, including a distinct `NULL` non-academic partition.

The database mapping for an exact Telegram user/chat pair is authoritative.
Client-supplied conversation UUIDs cannot replace it. Different users, chats,
conversations, and student partitions cannot read each other's messages.
Telegram identifiers are used to resolve the scope but are not placed in the
trusted workflow's `AgentState` or tutor-facing response.

The public chat API has no authenticated tutor identity. It accepts or creates
a conversation UUID and returns it for compatibility, but it neither loads nor
saves persistent memory. A returned UUID therefore does not prove persistence.

## Retained data and limits

The store retains only conversation UUID, normalized owner scope, student
partition, role (`user` or `assistant`), message text, safe selected-agent route
names, interaction status (`completed` or `partial`), and database ordering/time
fields. Message text is capped at 4,000 characters. It keeps the newest 20 individual messages for the exact scope and
returns them oldest first.

Writes take a PostgreSQL transaction-scoped advisory lock derived from the
exact conversation, owner, and student partition. Both messages and retention
therefore commit atomically, and concurrent turns cannot bypass the 20-message
limit for the same scope.

It never stores complete `AgentState` or `AgentResult` objects, reports, tool or
MCP payloads, RAG or policy chunks, prompts, raw exceptions, stack traces,
credentials, tokens, internal service keys, request IDs, workflow control
collections, database sessions, clients, or arbitrary metadata.

Completed interactions save the user and assistant messages. Partial
interactions save conversational text with an explicit partial status but no
academic summaries. Failed interactions save nothing. Load failures continue
with no fabricated history; save failures do not replace the generated reply.
Failures are logged using controlled messages without persistence details.

## Persistence and deployment

Production uses PostgreSQL through `SQLAlchemyConversationMemoryStore`.
`InMemoryConversationMemoryStore` implements the same isolation and retention
contract for deterministic tests only and is not production persistence.

There is no automatic migration or schema creation. The CSC VM/PostgreSQL
deployment operator must apply the reviewed forward SQL before configuring the
internal service key and enabling trusted Telegram memory:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/db/migrations/001_create_conversation_memory.sql
```

Rollback is manual and destructive; it removes all stored mappings and memory:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/db/migrations/001_drop_conversation_memory.sql
```

The rollback file is never executed by the application. Application startup
does not run SQL migrations or call `Base.metadata.create_all()`.

`INTERNAL_SERVICE_KEY` must be configured with the same secret for the backend
and Telegram adapter process. No example or default secret is provided. Missing
or invalid authentication fails closed to stateless behavior.

## Limitations and future extension

Direct API memory remains disabled until the application has a trusted tutor
principal. Retention is count-based rather than time-based, and no scheduled
cleanup exists. Memory contains literal bounded conversation turns; there is no
LLM summarization, semantic search, profiling, cross-student general context, or
workflow resumption. A future authenticated API may reuse the store contract
with a separately approved owner type and authorization policy.

Tests use the in-memory implementation to verify cross-service continuity,
isolation, ordering, retention, workflow status handling, serialization, and
failure safety without PostgreSQL, Telegram, credentials, LLMs, RAG, or Qdrant.
