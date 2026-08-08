# Issue #123: Basic load and performance QA

## Scope and audit

The repository had no Locust, k6, JMeter, pytest-benchmark, ApacheBench, wrk,
or custom load runner. HTTPX was already pinned and used by the project, so the
smallest maintainable choice was an `asyncio` + `httpx.ASGITransport` runner.
The load runner is explicit and is not executed by normal pytest collection.

The audit covered the FastAPI entry point, route registration, health, sessions,
progress dashboard, chat and Telegram routes, dependency construction, database
configuration, MCP transport, RAG/agent services, logging, Docker setup,
dependencies, and existing testing/deployment documentation. MCP is exposed by
stdio rather than HTTP and was not selected. Telegram and chat/agent flows can
cross real external boundaries, so they were deliberately excluded from load.

Representative real routes selected:

| Workload | Actual route | Rationale |
| --- | --- | --- |
| Lightweight | `GET /` | Minimal application routing and serialization |
| Lightweight service | `GET /api/v1/health/health/` | Real health handler and dependency resolution |
| Medium orchestration | `GET /api/v1/students/1/progress-dashboard` | Real validation, dependency injection, handler and dashboard serialization |
| Mixed | all three | Concurrent heterogeneous application traffic |

The doubled `health/health` segment is the route currently produced by the
nested prefixes in the production application; the runner uses the actual route
rather than inventing a cleaner endpoint.

## Implementation and safety

`backend/tests/load/runner.py` uses the production FastAPI application and real
route handlers. It replaces only the health and dashboard service dependencies
with deterministic in-memory doubles. It measures total/success/failed requests,
error rate, duration, RPS, minimum, average, p50, p95, p99, and maximum latency.
Each scenario performs warm-up requests, lightly validates every response, and
performs a health check after measured load.

The runner has no target-URL option and can only use an in-process ASGI transport.
It therefore cannot accidentally contact production. No Supabase, Qdrant,
Telegram, LLM, embedding provider, database, network socket, or paid service is
used. These values measure project-owned route/orchestration overhead with mocked
service latency; they are not production end-to-end performance.

Small unit tests validate percentile calculation, request accounting, response
correctness, and the post-load stability check. They do not execute the default
load scenarios.

## Environment

| Item | Value |
| --- | --- |
| Date/time zone | 2026-08-09, Europe/Helsinki |
| OS | macOS 26.5.2, arm64 |
| Python | CPython 3.11.15 |
| Logical CPU count | 10 (`os.cpu_count()`) |
| Memory | Not reported; sandbox did not permit reliable system query |
| Execution | Local, in-process HTTPX ASGI transport |
| Server/workers | One Python process; no network server or Uvicorn worker |
| Database | Deterministic service double; no database traffic |
| RAG/LLM/Telegram | Not invoked |
| Logging | Existing application INFO logging enabled |

## Scenarios

Every scenario was run three times. The table shows measured requests per run;
warm-up and post-load health requests are excluded from metrics.

| Scenario | Endpoint/workload | Concurrency | Requests/run | Warm-up |
| --- | --- | ---: | ---: | ---: |
| `light-root` | root | 5 | 100 | 3 |
| `moderate-health` | health | 10 | 200 | 3 |
| `dashboard-route` | progress dashboard | 10 | 200 | 3 |
| `mixed-routes` | round-robin mix | 15 | 300 | 3 |

## Performance results

Values below are arithmetic means of the three complete runs. The ranges in
parentheses show the lowest and highest run-level value; no fastest run was
selected. Latencies are milliseconds.

| Scenario | Total requests | Success | Failed | Avg | P50 | P95 | P99 | RPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `light-root` | 300 | 300 | 0 | 0.883 (0.664–1.318) | 0.809 | 1.521 | 1.833 | 6102.5 (3709.6–7319.4) |
| `moderate-health` | 600 | 600 | 0 | 3.990 (3.760–4.446) | 3.783 | 6.168 | 7.733 | 2482.2 (2217.0–2618.9) |
| `dashboard-route` | 600 | 600 | 0 | 2.636 (2.623–2.648) | 2.644 | 3.302 | 3.643 | 3715.8 (3696.7–3733.9) |
| `mixed-routes` | 900 | 900 | 0 | 3.789 (3.735–3.835) | 4.438 | 5.984 | 6.505 | 3882.4 (3832.1–3941.3) |

No performance SLO exists in the repository, so these observations are not
classified against an invented pass/fail threshold.

## Stability and correctness

- 2,400/2,400 measured requests succeeded; error rate was 0%.
- No HTTP 5xx, timeouts, transport failures, unhandled exceptions, or corrupted
  sampled responses occurred.
- Required root message, health status, dashboard success flag, and student IDs
  were checked for every relevant response.
- All 12 post-scenario health checks succeeded.
- The application remained responsive after load and no cross-request identifier
  leakage was observed.

## Evidence-backed bottleneck

| Bottleneck | Evidence | Impact | Recommendation |
| --- | --- | --- | --- |
| INFO log emitted for every health request | The normal three-run health workload averaged 3.990 ms and 2,482 RPS despite returning a smaller payload than the mocked dashboard route (2.636 ms, 3,716 RPS). A controlled 500-request diagnostic using the same health scenario measured 3.969 ms average, 5.321 ms p95 and 2,494 RPS with INFO logging, versus 2.343 ms average, 2.927 ms p95 and 4,228 RPS with only the logger level changed to WARNING. | High-frequency health polling can create avoidable formatting/I/O work and noisy logs. This is local mocked-route evidence, not a production capacity claim. | In a separate issue, consider DEBUG-level health logs, sampling, or access-log policy; validate with the same scenario before changing production behavior. |

The higher run-to-run variation for the very short root scenario is measurement
noise at microbenchmark duration, not evidence of instability. No other
bottleneck is labeled confirmed because real database, RAG and agent latency was
intentionally excluded.

## Reproduction

From the repository root with backend requirements installed:

```bash
DEBUG=false python -m pytest backend/tests -q
DEBUG=false python -m pytest backend/tests/load/test_load_runner_unit.py -q
DEBUG=false python -m backend.tests.load.runner --smoke
DEBUG=false python -m backend.tests.load.runner --output /tmp/issue123-run1.json
DEBUG=false python -m backend.tests.load.runner --output /tmp/issue123-run2.json
DEBUG=false python -m backend.tests.load.runner --output /tmp/issue123-run3.json
DEBUG=false python -m pytest backend/tests -q
```

No backend server command is needed because ASGITransport runs the application
in-process. For ordinary local manual API use, the repository Docker command is
`docker compose up backend`, or Uvicorn may be run from `backend/` with
`uvicorn app.main:app --host 127.0.0.1 --port 8000`. The load runner does not
connect to either server.

## Functional verification

Pre-change baseline:

```text
920 passed, 1 failed, 1 warning in 2.54s
```

The existing failure is
`test_missing_collaborator_accumulates_error_and_preserves_completed_results`:
the agent registry passes an academic gateway to `CalendarAgent`, whose current
initializer accepts no argument. It is unrelated to load testing and was not
changed. The warning is the existing FastMCP/Pydantic incomplete field warning.

Post-change results are recorded after the final regression run.

Post-change regression:

```text
922 passed, 1 failed, 1 warning in 2.50s
```

The only difference is the two new load-runner unit tests passing. The same
unrelated CalendarAgent test remains the sole failure, so Issue #123 introduced
no functional regression.

## Limitations

- Local in-process microbenchmark, not production capacity certification.
- No network stack, TLS, reverse proxy, multiple Uvicorn workers, Docker, or
  resource saturation measurement.
- Service doubles remove database and dashboard computation latency.
- No RAG, LLM, embeddings, Telegram, MCP, or third-party latency.
- Short scenarios are sensitive to host scheduling noise.
- CPU and memory utilization were not measured.

## Recommendations

Immediate: retain the safe runner for comparative regression measurements and
consider a separate health-logging issue supported by the diagnostic above.

Future: if an approved isolated environment becomes available, add distinct
networked scenarios for a local database-backed dashboard and mocked AI
orchestration. Keep those numbers separate from these route-overhead results.

## Acceptance criteria

- [x] Basic load test completed: four scenarios, each repeated three times.
- [x] Response times measured: per-scenario latency distributions and RPS.
- [x] Bottlenecks documented: health request logging supported by a controlled
  comparison.
- [x] Results added to QA report: this document.
