# Endpoint security matrix

The access-control policy, agreed before authentication is implemented so the
policy drives the code rather than being reverse-engineered from it.

Every one of the 34 routes is classified. The router split (Phase A1) means most
of this is applied per-router in one line rather than per-endpoint.

## Classifications

| Class | Meaning |
| --- | --- |
| **Public** | No credentials. Reachable by anything that can route to the host. |
| **Authenticated User** | Any signed-in account. Read-only views of stored data. |
| **Engineer** | Can run the engineering engines and generate documents. |
| **Administrator** | Can change system state or read operational internals. |
| **Internal Only** | Not reachable from the browser at all — service-to-service, network-restricted. |

Roles are ordered `viewer < engineer < admin < developer`; a higher role
inherits everything below it.

---

## The matrix

### Public — 1 route

| Method | Path | Why |
| --- | --- | --- |
| GET | `/api/health` | Liveness probes and load balancers must reach it unauthenticated. **Must be trimmed**: it currently leaks `llm_model`, `ollama_host` and `documents_indexed`. Public health returns status only; the detailed form moves to `/api/admin/health/detail`. |

### Authenticated User — 8 routes

Read-only views of stored engineering data. Commercially sensitive (client
names, prices), so never public — but no engine is invoked and nothing changes.

| Method | Path |
| --- | --- |
| GET | `/api/offers` |
| GET | `/api/offers/{offer_id}` |
| GET | `/api/offers/by-source/{source_file}` |
| GET | `/api/records` |
| GET | `/records` (the HTML table) |
| GET | `/api/knowledge/overview` |
| GET | `/api/uploads` |
| GET | `/api/datasheet/forms` |

### Engineer — job history (added for the Package Center)

| Method | Path | Note |
| --- | --- | --- |
| GET | `/api/jobs` | Engineering job history |
| GET | `/api/jobs/{job_id}` | One job and its artifacts |
| GET | `/api/jobs/{job_id}/artifact/{name}` | Download, checksum-verified |

Engineer-level because producing these documents IS the engineer's work, and the
offer corpus — equally sensitive, carrying client names and prices — is already
at that level. The parallel `/api/admin/jobs` view stays administrator-only.

### Engineer — 17 routes

Everything that runs an engine, calls the LLM, or produces a document. These
consume GPU and produce customer-facing output, which is why they are not merely
"authenticated".

| Method | Path | Note |
| --- | --- | --- |
| POST | `/api/tools/spec` | `generate_specification` |
| POST | `/api/tools/quote` | `generate_quotation` |
| POST | `/api/tools/drawing` | `generate_drawing` |
| POST | `/api/tools/lookup` | `lookup_project` |
| POST | `/api/tools/retrieve` | `retrieve_knowledge` |
| POST | `/api/tools/list` | `list_projects` |
| GET | `/api/tools/filters` | `list_filters` |
| POST | `/api/bom` | `generate_bom` |
| POST | `/api/package` | heavy: spec + drawing + quote + retrieval |
| POST | `/api/package/export` | writes to disk when `write:true` |
| POST | `/api/siting/place` | **service principal deliberately EXCLUDED** — the payload carries a customer photograph, and a leaked agent key must not be able to post pictures of a customer's premises into the platform |
| GET | `/api/drawing/catalog` | |
| POST | `/api/drawing/render` | |
| POST | `/api/drawing/export` | |
| POST | `/api/drawing/from-spec` | |
| POST | `/api/quotation/pdf` | |
| POST | `/api/specification/pdf` | |
| POST | `/api/datasheet/pdf` | |

**The seven `operation_id`s above are the Flowise agent tool names.** The agents
authenticate as a service principal, not as a person — see *Machine access*.

### Administrator — 4 routes

Change system state or expose operational internals.

| Method | Path | Why |
| --- | --- | --- |
| POST | `/api/admin/reload-index` | Mutates the running server's retrieval state. |
| POST | `/api/ingest` | Rewrites the vector store; `reset=true` **deletes the collection**. |
| GET | `/api/ingest/{job_id}` | Job internals. |
| POST | `/api/uploads` | Writes to the server filesystem. Needs auth, a size cap and an extension allow-list. |

All Phase-C admin console routes (`/api/admin/logs`, `/errors`, `/metrics`,
`/db/*`, `/flowise/*`, `/health/detail`) are **Administrator**, and the database
and Flowise browsers additionally require the `developer` role.

### Internal Only — 4 routes

The backend's own chat engine. **It is live, not dead code** — and it is an
unauthenticated LLM endpoint today. The frontend does not call it (the chats go
to Flowise), so nothing user-facing breaks by closing it.

| Method | Path | Why |
| --- | --- | --- |
| POST | `/api/query` | Unbounded LLM compute; no caller in the product. |
| POST | `/api/query/stream` | As above, streaming. |
| GET | `/api/session/{session_id}` | Reads another user's chat history if the id is guessed. |
| DELETE | `/api/session/{session_id}` | Destroys another user's chat history if the id is guessed. |

**Recommendation: require the `developer` role, and consider deleting the two
`/api/query*` routes.** They predate the Flowise architecture, have no caller,
and are the single largest unauthenticated compute surface. Keeping dead-but-live
routes behind auth is the safe default; removing them is better if nothing needs
them. *(Decision needed — see the questions at the end.)*

---

## Machine access: the Flowise agents

The three chatflows call `/api/tools/*` from `localhost` as Flowise Custom
Tools. They cannot present a user session, so they need a **service principal**:

- a long-lived API key (`X-API-Key`) bound to a `service` role holding exactly
  the seven Engineer-class tool routes and nothing else;
- **stored per tool row in Flowise, which means it goes into the `credential`
  table** — the same table the admin console must never expose. This is why
  "credentials masked server-side" is a hard rule and not a preference;
- rotating that key means editing the tool rows and re-running
  `ops/verify-agents.sh`.

Without this, turning on authentication **breaks all three agents** — the
symptom would be the documented "the agent says it cannot call tools", which is
the same signature as the backend being down. Worth knowing before it happens.

---

## Cross-cutting rules

1. **Deny by default.** The dependency is applied per-router; a new route
   inherits its router's class rather than defaulting to open.
2. **`/api/health` is the ONLY unauthenticated route.** The current
   `_AUTH_OPEN` set already encodes this.
3. **Rate limits scale with cost**: strict on Engineer routes (LLM/GPU),
   strictest on `/api/package` (spec + drawing + quote + retrieval in one
   request), and a login lockout on the auth routes.
4. **Audit everything non-public**, reads included.
5. **Ownership is out of scope for 1.0** — roles gate capability, not per-record
   ownership. Any signed-in engineer sees all offers, which matches a
   single-tenant deployment for one company.

## Summary

| Class | Routes |
| --- | --- |
| Public | 1 |
| Authenticated User | 8 |
| Engineer | 17 |
| Administrator | 4 |
| Internal Only | 4 |
| **Total** | **34** |

## Decisions needed before Phase B

1. **Delete `/api/query` and `/api/query/stream`, or keep them behind the
   `developer` role?** No caller in the product; largest unauthenticated
   compute surface.
2. **Should `viewer` exist in 1.0?** If every account is at least an engineer,
   the Authenticated-User class collapses into Engineer and there is one less
   role to test.
3. **Service-principal key rotation** — accepted as a manual step (edit the
   Flowise tool rows, re-run `ops/verify-agents.sh`), or automated?
