# Issue #235 — Tutor academic exploration E2E validation

The E2E suite exercises the real `ChatService`, deterministic intent detection,
academic entity resolution, conversation memory/context, route selection,
LangGraph workflow, tutor-data and specialized agents, and the academic gateway
contract. A deterministic in-memory gateway replaces only the database/MCP
transport boundary; no network, production database, Telegram API, LLM, or
credentials are required.

Validated workflows include student discovery by name and student number,
student contact details, course discovery by code and name, rosters,
enrollments, pass/fail results and analytics, grades, teacher discovery and
assignments, progress, risk, study rights, entity switching, multi-entity
context, failed/ambiguous resolution, missing context, session isolation, and a
multi-turn Telegram-handler journey.

Fixture assumptions are intentionally deterministic: DIN24 has a 50% pass rate,
MAT101 has a 25% pass rate, Anna passed DIN24 with grade 5, John failed, and
Matti teaches DIN24. The context assertions verify that only canonical identity
metadata is retained; academic records continue to be fetched through the
gateway on each query.

The Telegram test replaces the external backend transport with an in-process
adapter while retaining the actual Telegram handler and `ChatService` pipeline.
Existing webhook tests separately cover Telegram update parsing, HTTP transport,
authentication, and bot delivery.
