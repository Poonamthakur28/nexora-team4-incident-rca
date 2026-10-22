# Repository structure audit — Nexora Team 4

> Path note: this audit describes the repository before the `api/` and `ui/` layout. Backend code now lives under `api/src`, tests under `api/tests`, Prisma under `api/prisma`, and the frontend under `ui/`.

**Repository:** `nexora-team4-incident-rca`  
**Scope:** Incident management and AI root cause analysis (Team 4 only)  
**Audit date:** 22 October 2026  
**Method:** Static inspection of source, configuration, tests, and documentation. No files were moved, no packages were installed, and no migrations were applied.

This repository is a modular-monolith **foundation**. The README states the same limit: health API, versioned route base, OpenAPI shell, module type contracts, one deterministic mock RCA agent, Compose for PostgreSQL, a React navigation shell, and CI. Domain persistence, workflows, and live model calls are absent on purpose.

## 1. Executive summary

**Verdict: Structurally sound with improvements needed.**

The repository matches Team 4's ownership boundary. All 12 RCA modules have a dedicated folder under `src/modules`, the names match `docs/module-specifications/module-catalog.md`, and the inspected source does not implement HRMS, project or task management, engineering change intelligence, or platform authentication. Documentation, environment validation, PostgreSQL Compose, CI, and the web shell describe the same system.

The structure is a foundation, and the modules are contracts. A folder or a type file is not an implementation. Only RCA-006 has executable behavior (`src/modules/ai-rca/mock-ai-rca.agent.ts`) and a unit test. The Express process does not import any domain module.

Two issues should be corrected before feature work starts:

1. `src/app.ts` evaluates `openApiDocument` before that constant is initialized. The same evaluation order throws `ReferenceError: Cannot access 'openApiDocument' before initialization`. The Express process itself was not started, because dependencies are not installed.
2. External identifiers are modeled three different ways, and `src/shared/identifiers.ts` is unused. Feature work on top of the current types will fork the cross-team reference contract.

Persistence, lifecycle states, tenant isolation, and authentication are explicitly unconfirmed in `docs/erd/team4-erd.md`. That is an open product decision, and it is not a reason to redesign the folders.

## 2. Current repository map

Generated and dependency directories (`node_modules`, `dist`) are not present. There is no `package-lock.json` and no `.env`.

```text
nexora-team4-incident-rca/
├── .github/workflows/ci.yml          # lint, typecheck, unit/integration vitest, build
├── database/
│   ├── fixtures/README.md            # placeholder; no fixture records
│   ├── migrations/README.md          # placeholder; no SQL migrations
│   └── seeds/README.md               # placeholder; no seeds
├── docs/
│   ├── architecture/                 # system overview, lifecycle, this audit
│   ├── development-guide/local-setup.md
│   ├── erd/team4-erd.md              # proposed entity inventory, not an approved schema
│   └── module-specifications/module-catalog.md
├── prisma/schema.prisma              # PostgreSQL datasource only; no models
├── scripts/                          # empty; not referenced by package.json or docs
├── src/
│   ├── server.ts                     # listen, SIGINT/SIGTERM shutdown
│   ├── app.ts                        # Express, CORS, JSON, Pino, health, Swagger
│   ├── config/env.ts                 # Zod-parsed environment, local defaults
│   ├── config/logger.ts              # Pino, service name, ISO time
│   ├── middleware/error-handler.ts   # generic HTTP 500
│   ├── middleware/not-found.ts       # generic HTTP 404
│   ├── routes/api.routes.ts          # mounts /health only
│   ├── routes/health.routes.ts       # GET /api/v1/health
│   ├── shared/identifiers.ts         # OwnedId / ExternalRef; no importers
│   └── modules/                      # one folder per RCA module; types only
│       ├── incidents/
│       ├── ingestion/
│       ├── timeline/
│       ├── evidence-collection/
│       ├── evidence-engine/
│       ├── ai-rca/                   # types + mock agent
│       ├── root-candidates/
│       ├── fix-agent/
│       ├── test-agent/
│       ├── validation/
│       ├── reviews/
│       └── audit-history/
├── tests/
│   ├── unit/ai-rca.test.ts
│   ├── integration/health.test.ts
│   └── e2e/                          # empty directory
├── web/                              # React 19 + Vite navigation shell
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── src/                          # App shell, nav labels, unused API client
├── docker-compose.yml                # PostgreSQL 16 only
├── package.json                      # npm workspaces: ["web"]
├── tsconfig.json / tsconfig.build.json
├── vitest.config.ts
├── eslint.config.js
├── .env.example
├── README.md
└── CONTRIBUTING.md
```

| Path | Purpose observed in the files |
|---|---|
| `src/modules/*` | Team 4 ownership map. Each module currently exposes types. RCA-006 also exposes a mock agent. |
| `src/routes`, `src/middleware`, `src/config` | Process composition. No domain routes yet. |
| `src/shared` | Intended home for genuinely cross-module Team 4 types. The only file is unused. |
| `prisma/` | Declares the PostgreSQL provider and `DATABASE_URL`. No product models. |
| `database/` | Documented future home for SQL migrations, seeds, and synthetic fixtures. |
| `web/` | Single-page shell. Navigation labels change local React state. No router and no API calls from the UI. |
| `tests/` | One unit test and one HTTP health test. `e2e/` has no tests. |
| `docs/` | Scope, module boundaries, proposed ERD, lifecycle, and local setup. Consistent with the code's stated limit. |

There is no Dockerfile, no API image, and no checked-in completion report. `README.md` refers to a completion report for setup verification; that file is not in the repository.

## 3. Module coverage matrix

Statuses follow the rule that a directory is not an implementation. "Partially present" means a boundary and a type contract exist in a fitting place, and services, persistence, HTTP, and tests are still absent unless the row says otherwise.

| Module | Locations | What is implemented | Structural gaps | Dependencies | Status | Recommended action |
|---|---|---|---|---|---|---|
| RCA-001 Incident Management | `src/modules/incidents/incidents.types.ts`; web label "Incident Dashboard" / "Incident Details" | `IncidentSummary` with `id`, `title`, free-form `status`, `createdAt`, optional `externalRefs`. | No service, repository, route, migration, or test. Status is an unconstrained string. | Defines `ExternalReference`, imported by RCA-002. | Partially present | Keep the folder. Add a service and repository here when incident persistence is approved. Constrain status only after lifecycle states are confirmed. |
| RCA-002 Incident Ingestion | `src/modules/ingestion/ingestion.types.ts` | `IncidentIntake` for `manual` and `fixture` sources. | No intake service, validation schema, or route. No dedicated screen. | Type-only import of `ExternalReference` from RCA-001. | Partially present | Keep ingestion separate from incident storage. Move the shared external-id type to `src/shared` so intake does not depend on the incident module file. |
| RCA-003 Incident Timeline | `src/modules/timeline/timeline.types.ts`; web label "Incident Timeline" | `TimelineEntry` with incident id, occurred time, recorded time, label, optional detail. | No store and no derivation logic. ERD still asks whether `incident_timeline` is a table or a view. | `incidentId` string only. No import of RCA-001. | Partially present | Leave the module in place. Do not add a table until the entity-versus-view decision is confirmed. |
| RCA-004 Evidence Collection | `src/modules/evidence-collection/evidence-collection.types.ts`; web label "Evidence" | `EvidenceSubmission` with incident id, optional investigation id, description, source label, capture time. | Submission has no evidence id. `externalSourceRef` is a bare string. No repository or route. | String ids only. | Partially present | Give submissions an id before the evidence engine or RCA agent can point at them. Use the shared external-reference type for source ids. |
| RCA-005 Evidence Engine | `src/modules/evidence-engine/evidence-engine.types.ts` | `EvidenceAssessment` with summary, `relevance` number, limitations, and `processedAt`. | No normalization or correlation code. `relevance` has no range. No UI entry of its own. | `evidenceId` string. No import of RCA-004. | Partially present | Keep it separate from collection. Encode the relevance range when the ERD confirms it. |
| RCA-006 AI RCA Agent | `src/modules/ai-rca/ai-rca.types.ts`, `mock-ai-rca.agent.ts`; `tests/unit/ai-rca.test.ts`; web label "RCA Investigations" | `AiRcaAgent.analyze` returns drafts that are always `status: 'proposed'`, with rationale, confidence, uncertainty, missing information, and evidence polarity (`supports`, `contradicts`, `context`). The mock returns confidence `0` when evidence is empty and `0.25` otherwise, and it never marks a cause confirmed. | Mock is not registered in the app. No provider adapter beyond the interface. Empty-evidence branch is untested. Incident ref inside `InvestigationContext` is a bare string. Confidence is an unbounded number. | No import of other modules. RCA-007 imports its evidence-link type. | Partially present | Keep the agent interface as the provider boundary. Register a factory only when a real provider is chosen. Extend the unit test to the empty-evidence result. |
| RCA-007 Root Cause Candidates | `src/modules/root-candidates/root-candidates.types.ts`; web label "Root Cause Candidates" | `RootCauseCandidate` requires `reviewRequired: true` and reuses `CandidateEvidenceLink`. | Stored candidate drops `missingInformation` and `status` from the AI draft. No persistence or review hand-off. | Type-only import from RCA-006. | Partially present | Make the stored candidate a superset of the draft fields that must survive review. Share the evidence-link type from `src/shared` if both modules own it. |
| RCA-008 Fix Agent | `src/modules/fix-agent/fix-agent.types.ts`; web label "Fix Proposals" | `FixProposalDraft` tied to an investigation and candidate, with `requiresHumanReview: true`. | No proposal service. ERD entities `proposed_code_change` and `remediation_task` have no types. Their ownership is still unconfirmed. | String ids only. | Partially present | Keep proposals in this module. Add code-change or task types only after ownership is confirmed. |
| RCA-009 Test Agent | `src/modules/test-agent/test-agent.types.ts`; web label combined with validation | `TestPlanDraft` with cases, steps, and expected result. | No execution record, although the ERD proposes `test_execution`. No service. | `proposalId` string. | Partially present | Add execution types beside the plan when validation work starts. |
| RCA-010 Validation Workflow | `src/modules/validation/validation.types.ts` | `ValidationState` union and `ValidationSummary` with notes. | No transition rules, blockers entity, or service. UI merges this with testing. | `proposalId` string. | Partially present | Keep validation as its own module. The combined nav label can stay until screens exist. |
| RCA-011 Human Review & Approval | `src/modules/reviews/reviews.types.ts`; web label "Human Review and Approval" | `HumanReview` for `candidate`, `fix_proposal`, and `resolution`, with a decision union. | `rationale` and `reviewerRef` are optional for every decision, including approve and reject. No service enforces that AI output stays proposed until a person decides. | String subject ids. Reviewer is a bare optional string. | Partially present | Require reviewer and rationale when `decision` is not `pending`. Point `reviewerRef` at the shared external-reference type. |
| RCA-012 RCA History & Audit | `src/modules/audit-history/audit-history.types.ts`; web label "Investigation History and Audit" | `InvestigationHistoryEntry` with event type, optional actor, time, and a details bag. | No append-only store. `eventType` is a free string. `details` is `Record<string, unknown>`. ERD also lists `approval_history`, which may overlap this module. | String ids. | Partially present | Keep one audit module. Confirm whether approval history is a filtered view of this log or a separate entity before adding tables. |

The web shell in `web/src/app/navigation.ts` names the investigation flow. It does not implement a module. `web/src/services/api.ts` and `web/src/types/api.ts` are unused by `App.tsx`.

## 4. Findings and severity

### F-01 — OpenAPI document is read before it is initialized

- **Severity:** Critical
- **Location:** `src/app.ts` (Swagger registration around the `/docs` mount, constant declared after the middleware registration)
- **Evidence:** `app.use('/docs', swaggerUi.serve, swaggerUi.setup(openApiDocument))` runs while the module is evaluating. `const openApiDocument` is declared later in the same file. A minimal reproduction of that order throws `ReferenceError: Cannot access 'openApiDocument' before initialization`. Importing `src/app.ts` through the real dependency graph was **not verified**, because `node_modules` is absent and this audit did not install packages.
- **Why it matters:** Module evaluation stops before `listen`. Health checks, Swagger, and the integration test that imports `app` cannot run until this order is fixed.
- **Correction:** Declare `openApiDocument` before `swaggerUi.setup` uses it. Keep the spec next to the routes it describes.

### F-02 — External identifiers have three incompatible shapes

- **Severity:** High
- **Locations:** `src/shared/identifiers.ts`; `src/modules/incidents/incidents.types.ts`; `src/modules/ingestion/ingestion.types.ts`; `src/modules/evidence-collection/evidence-collection.types.ts`; `src/modules/ai-rca/ai-rca.types.ts`; `src/modules/reviews/reviews.types.ts`; `src/modules/audit-history/audit-history.types.ts`
- **Evidence:** `identifiers.ts` exports `ExternalRef` with `owner` and a branded id, and nothing imports it. Incidents export a second type, `ExternalReference`, with `ownerTeam` and a plain `id`. Ingestion uses that second type. Evidence source, AI incident ref, reviewer, and audit actor are plain strings.
- **Why it matters:** Team 4's boundary rule is that other teams' ids stay opaque and namespaced. Three shapes mean incident intake, evidence, and the RCA agent cannot pass the same reference through the pipeline without ad hoc conversion.
- **Correction:** Keep a single external-reference type in `src/shared/identifiers.ts` and use it wherever an id is owned outside the current record. Delete the duplicate once call sites move. This is a type consolidation, not a new integration.

### F-03 — Candidate draft and stored candidate do not carry the same trace

- **Severity:** High
- **Locations:** `src/modules/ai-rca/ai-rca.types.ts`; `src/modules/root-candidates/root-candidates.types.ts`
- **Evidence:** `RootCauseCandidateDraft` includes `missingInformation`, `uncertainty`, `status: 'proposed'`, and evidence links. `RootCauseCandidate` keeps uncertainty and evidence links, forces `reviewRequired: true`, and omits `missingInformation` and `status`.
- **Why it matters:** RCA-007 is the record a reviewer would see. Dropping missing information at the module boundary removes a required part of an evidence-backed explanation.
- **Correction:** Store the draft fields that must remain visible through review. Keep `reviewRequired` (or an explicit unconfirmed state) on the stored record.

### F-04 — Request validation errors collapse into HTTP 500

- **Severity:** Medium
- **Locations:** `src/routes/health.routes.ts`; `src/middleware/error-handler.ts`
- **Evidence:** The health route calls `healthQuerySchema.parse(req.query)` with a strict empty object. `error-handler.ts` logs the thrown value and always responds with `500` and `INTERNAL_SERVER_ERROR`. Zod is a dependency and is also used for environment parsing.
- **Why it matters:** The first domain routes will copy this pattern. Invalid input would look like a server failure, and the centralized handler would bypass the error shape already used for 404s.
- **Correction:** Map validation failures to a 400 response with a stable error code before adding module routes. Keep business rules out of the handlers.

### F-05 — Schema location is undecided, and the application opens no database connection

- **Severity:** Medium
- **Locations:** `prisma/schema.prisma`; `database/migrations/README.md`; `database/seeds/README.md`; `database/fixtures/README.md`; `package.json` (`db:generate`, `db:studio`); `src/` (no `PrismaClient` import)
- **Evidence:** The Prisma schema has a PostgreSQL datasource and no models. `database/migrations` contains only a README that says migrations belong there after ERD approval. Prisma's own migration directory is not present. No service constructs a client. `@prisma/client` is a runtime dependency.
- **Why it matters:** The first persisted module will otherwise have to choose between `prisma/migrations` and `database/migrations` under time pressure. The ERD document already says foreign keys are unconfirmed.
- **Correction:** Choose one migration tool with the tech lead before any model is added. Leave the schema empty until that ERD review. The unused client dependency can stay until then; removing it is optional.

### F-06 — Installs are not reproducible

- **Severity:** Medium
- **Locations:** repository root (no lockfile); `.github/workflows/ci.yml`
- **Evidence:** `package.json` uses semver ranges. There is no `package-lock.json`. CI runs `npm install --no-audit --no-fund` on Node 22.
- **Why it matters:** Two runs can resolve different dependency trees. CI success on a later date would not describe this tree.
- **Correction:** Commit a lockfile and install from it in CI. Do that as a dependency-pinning change, separate from feature work.

### F-07 — Tests cover one mock path and one health URL

- **Severity:** Medium
- **Locations:** `tests/unit/ai-rca.test.ts`; `tests/integration/health.test.ts`; `tests/e2e/`; `vitest.config.ts`
- **Evidence:** The unit test calls the mock with one evidence item and asserts `proposed`, the evidence id, and confidence below 1. The empty-evidence branch is untested. The integration test listens and fetches `/health` only. `/api/v1/health`, `/openapi.json`, and `/docs` have no test. `tests/e2e` is empty. No test imports the other eleven modules. `npm test` includes `tests/**/*.test.ts`, so it already runs the integration file; `test:integration` is a narrower rerun of the same file.
- **Why it matters:** Modules can be tested independently later, because they have no I/O. Today, a contract change in incidents, evidence, review, or audit would not fail a test.
- **Correction:** Add unit tests beside each module as behavior appears. Extend the mock test to the empty-evidence draft. Point one integration test at `/api/v1/health`. Add e2e tests only when a user flow exists.

### F-08 — Human review can be recorded without a reviewer or a rationale

- **Severity:** Medium
- **Location:** `src/modules/reviews/reviews.types.ts`
- **Evidence:** `decision` may be `approved`, `rejected`, or `needs_changes` while `reviewerRef`, `decidedAt`, and `rationale` stay optional. The module catalog requires decisions, rationale, and reviewer references.
- **Why it matters:** RCA-006 and RCA-008 correctly force proposals to stay unconfirmed. RCA-011 does not yet require the human fields that make that rule auditable.
- **Correction:** Require reviewer, decision time, and rationale for every non-pending decision. Keep the reviewer as an external reference.

### F-09 — Web build script uses TypeScript project builds without a composite project

- **Severity:** Medium
- **Locations:** `web/package.json`; `web/tsconfig.json`
- **Evidence:** `build` and `typecheck` run `tsc -b`. `web/tsconfig.json` does not set `compilerOptions.composite` and has no project references. The command was **not verified** (dependencies are not installed).
- **Why it matters:** TypeScript build mode expects a composite project. If `tsc -b` fails, `npm run build` and CI fail before Vite runs.
- **Correction:** After dependencies are installed, run `npm run build`. If build mode rejects the config, switch the web scripts to `tsc --noEmit` (typecheck) and leave emit to Vite.

### F-10 — Local database credentials are the application default

- **Severity:** Low
- **Locations:** `src/config/env.ts`; `.env.example`; `docker-compose.yml`
- **Evidence:** If `DATABASE_URL` is unset, `env.ts` falls back to a local PostgreSQL URL. Compose defaults the same local user, password, database, and publishes port `5432`. `.env` is gitignored and is not present. No production secret was found in source.
- **Why it matters:** A process started without a private environment file uses a known local password. That matches a development scaffold. It is unsafe if this Compose file or default is reused outside a developer machine.
- **Correction:** Keep example values in `.env.example` and Compose defaults. Remove the credential-bearing fallback from `env.ts` before any shared or deployed environment, so a missing variable fails startup.

### F-11 — Empty `scripts/` directory and a missing verification record

- **Severity:** Low
- **Locations:** `scripts/`; `README.md` ("completion report" paragraph)
- **Evidence:** `scripts/` contains no files and is not referenced. The README says setup command results live in a completion report. No such document is in `docs/` or the repository root.
- **Why it matters:** A new developer cannot find the verification record the README promises. The empty directory has no owner.
- **Correction:** Either add the verification notes or point the README at this audit's verification section. Remove `scripts/` until a script exists, or document it.

### F-12 — API client and log redaction are unused scaffolding

- **Severity:** Low
- **Locations:** `web/src/services/api.ts`; `web/src/types/api.ts`; `src/config/logger.ts`; `src/app.ts` (`pino-http`)
- **Evidence:** `apiRequest` is not imported by the UI. The logger sets level, service name, and ISO time, and it has no redaction paths. Current routes do not log bodies. Request logging is enabled for every request.
- **Why it matters:** The client will drift from the API if screens are built against a stale helper. Later evidence and incident text can land in logs if errors include request data. `error-handler.ts` already logs the full error object.
- **Correction:** Use the client when the first screen calls the API. Add a redaction list before routes accept incident or evidence bodies.

No hardcoded third-party API keys, tokens, or private keys were found. Zod validation of `NODE_ENV`, `PORT`, and `CORS_ORIGIN` is present in `src/config/env.ts`.

## 5. Team ownership violations

**No confirmed out-of-scope implementation.**

| Item | Classification | Evidence |
|---|---|---|
| Opaque external ids (`ExternalReference`, unused `ExternalRef`, string refs) | Acceptable interface, currently inconsistent | Types only. No HRMS, project, task, repository, or deployment entities. |
| `ownerTeam` generic on incidents | Acceptable interface | The field names an external owner. It does not embed another team's schema. |
| ERD rows `remediation_task` and `proposed_code_change` | Unresolved ownership, not a violation | Documented as unconfirmed in `docs/erd/team4-erd.md`. No code implements them. |
| `reviewerRef` and `actorRef` strings | Acceptable interface | They reserve a place for a person id owned elsewhere. They are not an identity system. |
| PostgreSQL Compose, Prisma datasource, Express, React | Team 4 application infrastructure | Local to this service. |
| Authentication, tenants, observability connectors | Absent, as required | `docs/architecture/system-overview.md` and `CONTRIBUTING.md` forbid implementing them here. |
| Web copy and nav labels | Team 4 UI shell | Labels match incident, evidence, RCA, fix, test, review, and audit. |

`database/fixtures/` has no records, so there are no cross-team fixture violations.

## 6. Dependency and module flow

The running process and the domain modules are separate graphs.

```text
server.ts
  └── app.ts
        ├── config/env.ts → config/logger.ts
        ├── middleware/error-handler.ts → logger
        ├── middleware/not-found.ts
        └── routes/api.routes.ts → routes/health.routes.ts

tests/integration/health.test.ts → app.ts
tests/unit/ai-rca.test.ts → modules/ai-rca/mock-ai-rca.agent.ts → ai-rca.types.ts

modules/ingestion → modules/incidents          (type only)
modules/root-candidates → modules/ai-rca       (type only)
src/shared/identifiers.ts                      (no importers)
```

Observations:

- **No circular imports** were found. Every `src` import was read.
- **No domain module is mounted.** Incident, evidence, RCA, review, and audit code cannot affect HTTP behavior today.
- **Two type edges match the lifecycle direction.** Ingestion depends on the incident reference type. Stored candidates depend on the AI evidence-link type. Those edges are reasonable and should become shared contracts if more than one consumer needs them (`docs/module-specifications/module-catalog.md` already says this).
- **RCA-003, RCA-004, RCA-005, RCA-008, RCA-009, RCA-010, RCA-011, and RCA-012 do not import each other.** Their connection is implied by string ids (`incidentId`, `evidenceId`, `investigationId`, `candidateId`, `proposalId`). That keeps coupling low and also means referential integrity exists only in documentation.
- **AI logic is separated from incident storage.** The mock agent depends only on its own interface. That is the right seam for a later provider or a test double.
- **The web app does not depend on `src/modules`.** It duplicates the lifecycle as navigation labels.

Intended lifecycle from `docs/architecture/incident-rca-workflow.md`, and where each step lives:

| Step | Module | Code today |
|---|---|---|
| Ingest | RCA-002 | Intake type |
| Manage incident and chronology | RCA-001, RCA-003 | Summary and timeline types |
| Collect evidence | RCA-004 | Submission type |
| Assess evidence | RCA-005 | Assessment type |
| Investigate | RCA-006 | Interface and mock |
| Hold candidates | RCA-007 | Candidate type, missing draft fields |
| Human review of candidates | RCA-011 | Review type, optional rationale |
| Propose a fix and tests | RCA-008, RCA-009 | Draft types |
| Validate | RCA-010 | State union and summary |
| Approve, resolve, retain history | RCA-011, RCA-012 | Review and history types |

Missing ownership inside that flow: there is no `rca_investigation` type even though the ERD proposes one and several modules already carry `investigationId`. Investigation identity is currently an unowned string. That should be an explicit Team 4 type, hosted with RCA-001 or a small investigation contract, before several modules invent their own investigation record.

Overlap to confirm, not a second implementation: `approval_history` versus RCA-012, and `incident_timeline` as a table versus a view. Both are already called out in the ERD notes.

## 7. Recommended target structure

The folder tree can stay. The changes below are consolidations. They are not a new architecture.

```text
src/
├── app.ts
├── server.ts
├── config/
├── middleware/                 # include validation-error mapping
├── openapi/                    # document moved out of app.ts
├── routes/                     # thin routers added per module when behavior exists
├── shared/
│   └── identifiers.ts          # the only external-reference type
└── modules/
    └── <module>/
        ├── <module>.types.ts
        ├── <module>.service.ts      # only when rules exist
        └── <module>.repository.ts   # only when a confirmed model exists
prisma/                         # keep as the ORM home if Prisma Migrate is chosen
database/fixtures/              # synthetic fixtures after contracts exist
```

| Change | Why | Team 4 responsibility |
|---|---|---|
| Move the OpenAPI object above its use, then into `src/openapi/` when more paths appear. | Fixes startup and keeps `app.ts` as composition. | API foundation for every module. |
| Adopt `src/shared/identifiers.ts` and remove `ExternalReference` from the incident file. | One opaque external id for intake, evidence, review, and audit. | Boundary with other teams. |
| Add an `InvestigationId` (and later an investigation record) in one module, then reference it. | `investigationId` is already shared and has no owner. | RCA-001 through RCA-012 lifecycle. |
| Put new behavior in `<module>.service.ts` and persistence in `<module>.repository.ts`. Routes parse input and call the service. | Matches `CONTRIBUTING.md`. Avoids HTTP handlers becoming the domain. | All modules as they are implemented. |
| Pick either `prisma/migrations` or `database/migrations` and document the other as unused. | Prevents two schemas. | Persistence for incidents, evidence, candidates, reviews, and history. |
| Leave empty service files uncreated. | Empty placeholders would look like implementations. | Honest module status. |
| Keep `web/` as a shell until a module has an API. Then call `web/src/services/api.ts` from the screen that needs it. | The client is already the right seam. | UI for the same 12 responsibilities. |

Do not add cross-team clients, auth services, or copies of other teams' tables as part of this cleanup.

## 8. Prioritized action plan

### 1. Fix before feature development

Mandatory:

1. Fix F-01 so `src/app.ts` can finish loading.
2. Unify external references (F-02) and align the candidate record with the AI draft (F-03).
3. Name a single owner for `investigationId` before modules persist investigations separately.
4. Map validation errors to HTTP 400 (F-04) before the first domain route.

Still a tech-lead decision, and it blocks schema work rather than TypeScript features:

- Approve or replace the entity list in `docs/erd/team4-erd.md`.
- Choose Prisma Migrate or SQL files under `database/migrations` (F-05).

Optional at this step: delete empty `scripts/`, or document it (F-11).

### 2. Fix before integration or deployment

Mandatory once the service leaves a laptop:

1. Commit a lockfile and use a lockfile install in CI (F-06).
2. Run lint, typecheck, tests, and build on a machine with dependencies installed. Resolve F-09 if `tsc -b` fails.
3. Require reviewer and rationale on non-pending human decisions (F-08) before any AI or fix proposal can be accepted.
4. Remove the credential-bearing `DATABASE_URL` fallback before shared environments (F-10).
5. Add authentication, authorization, and tenant isolation only from the platform contract. Do not invent them inside Team 4. Do not deploy incident or evidence data before that contract exists.
6. Add log redaction before request bodies can contain incident text (F-12).

### 3. Improve as the project grows

Optional, in the order modules are built:

- Unit tests for each new service, including the mock agent's empty-evidence path (F-07).
- OpenAPI paths beside each route.
- A versioned health test.
- Wire each nav screen to its module API when that API exists.
- Decide approval-history versus investigation history, and timeline table versus view, when the ERD is approved.
- Introduce a real `AiRcaAgent` implementation behind the existing interface. Keep the mock for tests.

## 9. Verification results

| Check | Result |
|---|---|
| Node.js | **Verified.** `v22.22.0` (engines field asks for `>=20`). |
| npm | **Verified.** `10.9.4`. |
| `node_modules` and `web/node_modules` | **Absent.** |
| `.env` | **Absent.** `.env.example` is present. |
| Lockfile | **Absent.** |
| `npm install` | **Not run.** Out of scope for this audit. |
| `npm run lint` | **Not verified.** ESLint is a local devDependency and is not installed. |
| `npm run typecheck` | **Not verified.** TypeScript is not installed locally. |
| `npm test` and `npm run test:integration` | **Not verified.** Vitest and Express are not installed. |
| `npm run build` | **Not verified.** See F-09 for a static risk in the web `tsc -b` script. |
| `npm run db:generate` | **Not run.** Schema has no models; generate would still require installed Prisma. |
| Docker Compose / migrations | **Not run.** No migration files exist to apply. |
| OpenAPI initialization order | **Language behavior verified.** A standalone reproduction of "call a function with `const` before its initializer" throws `ReferenceError: Cannot access 'openApiDocument' before initialization`. The repository's `src/app.ts` uses that order. Loading `src/app.ts` itself was **not verified**. |
| Secret scan of tracked source, Compose, and `.env.example` | **No third-party credentials found.** Local database defaults are covered by F-10. Secret values are omitted here. |
| Import graph | **Verified by reading every `src` import.** No cycles. Domain modules are not imported by `server.ts` or `app.ts`. |

CI in `.github/workflows/ci.yml` is written to run install, lint, typecheck, `npm test`, and build on Node 22 for pushes and pull requests to `main`. Those jobs were not executed from this workspace.

## 10. Final verdict

1. **Is this structure suitable for Team 4?** Yes. It is a Team 4 modular monolith with a clear place for each required responsibility, a PostgreSQL seam, a versioned API prefix, and a UI shell. It is suitable as the base for implementation after the startup defect and the shared identifier contract are fixed.

2. **Does it cover all 12 modules?** Every module is represented by a folder and a type contract in the right area. None is fully implemented. RCA-006 is the only module with executable behavior and a test. Coverage status for all twelve is **partially present**.

3. **Are module responsibilities separated correctly?** The folders match the catalog, and there is no circular dependency. Separation is not yet enforced in the process, because routes do not call modules. Two cross-module type imports are directionally sound and should move to `src/shared` as the shared contract. Investigation id has no owning type.

4. **Is there any unnecessary complexity?** The twelve module folders are justified by the twelve required responsibilities. The extra complexity that should be removed or decided is the unused identifier type, the second external-reference type, the dual migration locations, the empty `scripts/` directory, and an unused web API helper. Prisma-without-models and an empty `tests/e2e` directory match the written plan.

5. **What are the top five corrections?**
   1. Initialize the OpenAPI document before Swagger setup (F-01).
   2. Use one shared external-reference type everywhere an id is owned outside Team 4 (F-02).
   3. Preserve missing information and proposal status on stored root-cause candidates (F-03).
   4. Assign an owner type for `investigationId` before persistence.
   5. Choose one migration path and confirm the ERD before adding models (F-05), and map validation failures to HTTP 400 before adding routes (F-04).

6. **Can development begin without restructuring?** Yes. Implement inside the existing module folders. Do not rename the modules or split the process. Fix F-01 and the shared contracts first so new code does not depend on a process that cannot load or on divergent id types.

7. **Which decisions require the tech lead's confirmation?**
   - The entity list, cardinalities, delete behavior, and required fields in `docs/erd/team4-erd.md`.
   - Whether `incident_timeline` is stored or derived.
   - Lifecycle state names and legal transitions for incidents, investigations, candidates, reviews, fixes, tests, and resolutions.
   - Whether one incident may have concurrent investigations.
   - Whether `remediation_task` and `proposed_code_change` are Team 4 records or external references.
   - Whether `approval_history` is part of RCA-012 or a separate append-only record.
   - Prisma Migrate versus SQL in `database/migrations`.
   - Tenant key, claim source, and authentication, with the platform owner (Team 5). This repository should keep consuming an agreed contract rather than building that platform.
   - Which AI provider, if any, will implement `AiRcaAgent`. The interface can stay as it is until that choice is made.
