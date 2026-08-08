# Issue #124: Basic defensive security QA

## Scope

This audit reviewed FastAPI setup and OpenAPI, every registered API group,
configuration/environment loading, Git ignore/tracking, database dependencies,
Telegram webhook/client/notifications, chat memory and sessions, MCP tools, RAG
and provider configuration, SQL construction, logging and exception handlers,
Docker/deployment files, tests, dependencies, and security tooling. It was a
local code review plus safe automated regression testing, not a penetration test.

No production service, Telegram API, database, Qdrant instance, LLM, embedding
provider, or real user data was contacted. All test credentials and identities
are visibly synthetic.

## Security checklist

| Area | Check | Status | Evidence/notes |
| --- | --- | --- | --- |
| Secrets | Real `.env` files excluded from Git | PASS | `.gitignore` covers `.env` and `*.env`; Git-aware checks found no tracked `.env`. |
| Secrets | No obvious hard-coded production credential | PASS within scan scope | 307 tracked files scanned for common Telegram, Google, OpenAI, JWT and private-key patterns; zero candidates. Manual configuration review found placeholders/default-empty values. |
| Secrets | Example environment file contains placeholders | PASS | `backend/.env.example` is the only tracked env-like file and contains empty/local example values. |
| Secrets | Credentials loaded from configuration | PASS | database URL, Telegram token/webhook secret/internal key, Gemini key and Qdrant URL come from `Settings`. |
| Secrets | Secrets absent from representative API/error responses | PASS | focused tests cover root, Telegram rejection and dashboard failure. |
| Secrets | Secrets not intentionally logged | PASS for reviewed paths | webhook logs a fixed rejection message; backend client logs URL only. Focused tests assert fake secrets are absent. |
| API access | Authentication mechanism identified | PASS | runtime webhook shared secret; chat internal key only marks trusted Telegram context. No general API authentication scheme. |
| API access | Public/protected endpoints identified | PASS | access matrix below. |
| API access | Missing/invalid webhook credentials checked | PASS | both return 403 before Telegram application lookup. |
| Authorization | Roles/resource ownership identified | FAIL | no general role, identity or ownership enforcement exists on session/dashboard routes. |
| Authorization | Unauthorized/cross-resource access considered | FAIL | numeric path identifiers can select another session/student without an authenticated principal. |
| Telegram | Token comes from configuration and is not hard-coded/returned/logged | PASS for reviewed path | token is passed from settings to the SDK builder; focused failure tests use fake values only. |
| Sensitive data | Student/session fields and responses reviewed | PASS (review completed) | exposure risks SEC-001 through SEC-003 remain. |
| Sensitive data | Errors avoid stack traces/internal detail | PASS for tested handlers | dashboard and global handler return generic errors; default debug setting remains a risk (SEC-004). |
| Logging | Credentials/auth headers excluded | PASS for reviewed log calls | no complete headers or secret values are formatted. |
| Logging | Personal/student identifiers minimized | FAIL | chat and Telegram INFO logs include user/chat IDs; chat also includes username (SEC-005). |
| Configuration | CORS reviewed | PASS | no CORS middleware: browsers receive no cross-origin permission by default. |
| Configuration | Debug/error behavior reviewed | FAIL | `debug=True` is the configuration default (SEC-004). |
| Dependencies | Existing vulnerability scanner run | NOT VERIFIED | no pip-audit, Safety, Dependabot or equivalent configuration/command was available; no network scanner was introduced. |
| Database | Parameterization reviewed | PASS for inspected repositories | SQLAlchemy `text()` statements use bound parameters; dynamic student-search clauses are fixed fragments, with values in `params`. |
| Files | Upload/path API reviewed | N/A | no upload or caller-supplied filesystem route exists. RAG ingestion paths are local operator-run tooling. |
| Prompt/RAG | Trust boundary reviewed | PASS (review completed) | retrieved document text enters prompts; no credential is inserted, but document trust remains an architectural limitation. |
| MCP | Access assumptions reviewed | PASS (review completed) | stdio tools rely on host/process access rather than tool-level identity; see SEC-006. |

`PASS` means the stated check was evidenced within this limited scope, not that
the whole application is secure.

## API access matrix

OpenAPI contains no declared security scheme. Custom header checks therefore do
not appear as OpenAPI authentication.

| Endpoint/resource | Expected/current access | Actual behavior | Sensitive data/action | Status |
| --- | --- | --- | --- | --- |
| `GET /` | Public | Public | app name/environment label | PASS |
| health endpoints | Public | Public | service/database availability | PASS; consider operational exposure in deployment |
| `POST /api/v1/telegram/webhook` | Protected when enabled | Disabled returns 503; missing/invalid shared secret returns 403; valid secret dispatches | external update/action | PASS |
| `POST /api/v1/chat/messages` | Public basic chat; internal key adds trusted Telegram memory scope | requests without a valid key still run chat and may supply Telegram IDs; invalid keys fail closed only for trusted scope | message, supplied identity, optional student/workflow | RISK SEC-003 |
| `GET /api/v1/sessions/{telegram_user_id}` | No documented auth | public lookup by caller-selected numeric ID | username, chat ID, message history/context | FAIL SEC-001 |
| `DELETE /api/v1/sessions/{telegram_user_id}` | No documented auth | public deletion by caller-selected numeric ID | deletes in-memory user session | FAIL SEC-001 |
| progress dashboard | No documented auth | public lookup by caller-selected student ID | profile, progress, study right, risk and actions | FAIL SEC-002 |
| MCP stdio tools | Trusted local MCP client/process | no per-tool identity/authorization | profile/search/dashboard/report academic data | RISK SEC-006 |

## Secret handling

Values are intentionally omitted.

| Secret type | Source | Tracked? | Exposed in tested output? | Status |
| --- | --- | ---: | ---: | --- |
| Database URL/credentials | `DATABASE_URL` / local default | No real value tracked | Not found | PASS with logging limitation |
| Telegram bot token | `TELEGRAM_BOT_TOKEN` | No | Not found | PASS |
| Telegram webhook secret | `TELEGRAM_WEBHOOK_SECRET` | No | Not found | PASS |
| Internal service key | `INTERNAL_SERVICE_KEY` | No | Not found | PASS |
| Gemini API key | `GEMINI_API_KEY` | No | Not found | PASS |
| Qdrant URL/config | `QDRANT_URL`, collection setting | local placeholder only | Not found | PASS; no Qdrant API-key setting exists |
| Supabase credentials | none in active `Settings` | No | Not found | N/A; backend uses `DATABASE_URL` rather than a Supabase SDK key |

Local `.env` and `backend/.env` were absent during this audit. Presence would
not itself be a vulnerability because both paths are ignored; tracking status is
the relevant control.

## Findings

| ID | Severity | Component | Finding/evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- | --- |
| SEC-001 | High | session API | GET and DELETE accept only `telegram_user_id`; there is no authenticated principal, ownership check or OpenAPI security scheme. | Anyone who can reach the API and guess an ID can read conversation/session metadata or delete that session. | Create a separate authentication/authorization issue; bind session access to a verified identity and deny cross-user IDs. Consider removing these routes from public deployment until protected. |
| SEC-002 | High | progress dashboard API | Route exposes dashboard results for arbitrary positive `student_id` without authentication/authorization. | Enumerable academic profile, progress, study-right, risk and recommended-action data may be disclosed. | Add organization-approved authentication and tutor/student scope checks in a dedicated issue. Avoid relying on unguessable numeric IDs. |
| SEC-003 | Medium | chat API/session service | Internal key is constant-time checked, but it only enables trusted memory. Untrusted callers still invoke chat and supply Telegram user/chat IDs; session state is keyed by that supplied user ID. | Identity spoofing, session pollution, workflow resource use, and linkage with public session routes. | Define intended public-chat contract; authenticate or stop accepting authoritative Telegram identifiers from untrusted callers. Add rate limiting separately. |
| SEC-004 | Medium | configuration/error handling | `Settings.debug` defaults to `True`. FastAPI/Starlette debug mode can return detailed tracebacks for unhandled failures even though production handlers are generic. | Misconfigured deployments may expose code paths and internal exception details. | Default debug to false or enforce false outside explicit development; add a deployment/config regression test. |
| SEC-005 | Low | application logs | chat INFO logs user ID, chat ID and username; Telegram webhook INFO logs update/user/chat IDs. | Personal identifiers can be retained or broadly visible in centralized logs. | Define log-retention/access policy and reduce/hash identifiers where operationally unnecessary. |
| SEC-006 | Medium | MCP tools | data-bearing stdio tools have no per-caller identity or resource scope and rely entirely on host/upstream trust. | A broadly exposed MCP process could disclose/search student records and reports. | Document and enforce trusted local transport/process access; add authorization before any remote/shared exposure. |
| SEC-007 | Low | dependency assurance | no configured vulnerability scanner was found and no local scanner executable was available. | Known dependency vulnerabilities may not be detected consistently. | Enable Dependabot or a pinned CI `pip-audit` job in a separate infrastructure change. |
| SEC-008 | Informational | RAG prompt boundary | retrieved document content is injected into prompts and source metadata is returned; no credential is inserted. | Malicious/untrusted documents could influence agent output or attempt cross-context instruction. | Restrict ingestion sources, retain source attribution, and add prompt-injection/data-separation evaluation before multi-tenant use. |

No committed credential or direct token leakage was confirmed. The access-control
findings are architectural and intentionally were not silently redesigned under
this QA issue.

## Automated tests added

`backend/tests/security/test_security_contracts.py` adds five cases:

1. missing Telegram webhook secret is rejected before dispatch and not exposed;
2. invalid Telegram webhook secret is rejected and neither configured nor
   supplied fake secret enters response/log output;
3. public root does not serialize configured fake secrets;
4. dashboard dependency exceptions return a generic response without detail;
5. backend connection failures neither log nor return the internal service key.

Tests use only fake tokens/identities and mocked/in-process boundaries.

Focused result:

```text
5 passed in 1.18s
```

## Functional baseline and verification

Pre-change backend baseline:

```text
922 passed, 1 failed, 1 warning in 2.52s
```

The sole failure is the existing unrelated CalendarAgent collaboration test:
the registry supplies an academic gateway but `CalendarAgent` accepts no
constructor argument. The warning is the existing FastMCP/Pydantic incomplete
field warning. Post-change results are added after final verification.

Focused security plus affected API/configuration/integration suites:

```text
41 passed in 1.23s
```

Post-change backend regression:

```text
927 passed, 1 failed, 1 warning in 2.21s
```

The five new security tests account for the pass-count increase. The identical
CalendarAgent baseline failure and warning remain; no new regression appeared.

Tracked-file scan evidence:

```text
307 tracked files scanned
0 common credential-pattern candidates
0 tracked .env files
```

The scan covered common Telegram token, Google/OpenAI key, JWT and private-key
formats. It is not proof that no secret exists in any possible format.

## Production changes

None. This issue adds tests and documentation only. Major authentication,
authorization, logging and configuration changes require explicit product and
deployment decisions.

## Limitations

- No destructive or remote penetration testing.
- No real credential, production data, external provider or network call.
- No dependency CVE database scan; dependency vulnerability status is unknown.
- No historical Git commit scan, secret entropy scanner, infrastructure/cloud
  policy review, TLS/reverse-proxy test, rate-limit test, or denial-of-service test.
- No multi-tenant RAG isolation exists to test in the current architecture.
- Logging sinks, retention and access controls are deployment-specific and were
  not available.

## Acceptance criteria

- [x] Security checklist completed with PASS/FAIL/N/A/NOT VERIFIED states.
- [x] Sensitive credentials protected in tracked files and representative tested
  responses; no broader security claim is made.
- [x] Basic access checks documented in the endpoint matrix.
- [x] Security risks listed with evidence, severity and follow-up recommendations.
