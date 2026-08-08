# Workflow Execution Logs (Issue #108)

## Purpose and boundary

Issue #108 records durable, aggregate execution history for the approved
workflows. It is not a scheduler, academic decision engine, alert store,
briefing store, generic audit platform, or Telegram delivery-history system.

- Issue #100 continues to own scheduling.
- Issues #102 through #106 retain their business outcomes and result contracts.
- Issue #107 retains recipient resolution, rendering, and delivery; #108 records
  only one aggregate delivery-batch outcome without recipient or provider data.
- The Issue #103 `weekly_workflow_reports` table remains report storage, not
  generic execution history.

## Stored execution lifecycle

Each instrumented invocation receives a random UUID `execution_id`. A root
execution uses the same UUID as its `correlation_id`; nested #104, #106, and
#107 calls inherit that correlation ID and record their immediate parent UUID.
Existing daily, weekly, and risk execution keys remain optional logical keys,
not unique execution IDs.

`workflow_execution_logs` creates one mutable record per execution:

1. `running` is written at start.
2. A final `completed`, `partial`, `failed`, or `unavailable` state updates it.
3. If the start write was unavailable but the final write succeeds, the final
   record is inserted with the original start timestamp.

An empty successful workflow remains `completed` with zero aggregate counts.
`partial` and `unavailable` are never presented as successful completion.
The current workflows have no final cancellation or timeout contract, so those
states are not invented. A process stop can leave a `running` record; Issue
#108 deliberately adds no stale-run cleanup worker.

## Privacy and data minimization

The table stores only workflow identifiers, trigger type, UTC timestamps,
monotonic elapsed duration, fixed aggregate counts, status, and an allowlisted
error code with a controlled generic summary.

It never stores student or Tutor names/identifiers, emails, academic records,
meeting notes, complete result payloads, AgentState, alert evidence, briefing
text, Telegram destinations, Telegram provider IDs, message bodies, secrets,
environment values, raw exceptions, or stack traces. There is no arbitrary
JSON payload column.

The existing application logger is still ordinary stdout logging; it is not
durable workflow history. Any logging-persistence failure emits only a safe
workflow name and execution UUID to that application logger.

## Reliability limits

History persistence is best effort. A workflow's actual academic or delivery
result is returned or raised unchanged if the history write fails. A secondary
logging failure cannot hide the original workflow exception, and no retry loop
or exactly-once claim is introduced.

The unique UUID prevents two records for the same instrumented invocation, but
does not create a distributed execution lock. Multiple application instances
can still execute the same logical daily or weekly work. No retention,
archival, deletion schedule, access API, or stale-running cleanup policy is
currently implemented; these are operational limitations to resolve later.

## Testing

The recorder accepts an injected repository protocol, allowing deterministic
unit tests with an in-memory fake. Tests use controlled UTC clocks and
monotonic values and do not require a scheduler, production database, Telegram
token, network call, LLM, RAG, or Qdrant.
