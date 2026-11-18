# RMA Pipeline (FastAPI)

A web system that receives trial balances and income statements by upload or e-mail, extracts the data with an LLM, computes financial indicators and generates each company's monthly activity report (RMA, *Relatório Mensal de Atividades*) as a `.docx`.

It is the second version of [rma-pipeline-apps-script](https://github.com/FIlIpeDiBr/rma-pipeline-apps-script). The first one ran on Google Apps Script with a spreadsheet as its database; this one was rewritten to get past those limits. It was built for a Brazilian accounting firm and is published here without client data. Code identifiers and documentation are in Portuguese because the domain is Brazilian accounting.

*[Versão em português](README.md)*

## Architecture

A React + Vite portal talks to a FastAPI service over REST and SSE. The API enqueues jobs in PostgreSQL, and a Procrastinate worker runs them: triage and extraction with Claude, file storage on S3-compatible storage, e-mail polling through Microsoft Graph. Login is Microsoft Entra ID (OIDC). One Docker image serves both roles; `SERVICE_ROLE` decides whether the container starts the API or the worker. The queue lives in Postgres, so there is no Redis to operate.

| Layer | Technology |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| Queue | Procrastinate (jobs in PostgreSQL), periodic task for the mailbox |
| AI | Claude: a cheap model for triage, a larger one for extraction and analysis text |
| Reports | docxtpl (`.docx` templates with Jinja) and matplotlib |
| Auth | Microsoft Entra ID (OIDC), signed session cookie |
| Frontend | React 18, TypeScript, Vite |
| Operations | Docker, Render (web + worker), Sentry, structured logs (structlog) |

## Engineering decisions

**Idempotent, resumable jobs.** Processing the same document twice replaces its data. Documents with the same business key (company, month, year, type) are deduplicated and the newest wins.

**Auditable AI cost.** Every model call stores model, tokens, estimated cost, duration, prompt and response in the `ai_calls` table. Models and the price table are configurable through environment variables.

**Indicators as data.** The 23 definitions live in a table and each organization can override a formula without touching code. Formulas go through a purpose-built evaluator, no `eval`.

**Human review for e-mail intake.** The mailbox is polled every 5 minutes, but no attachment enters the pipeline until someone approves it.

**Isolation per organization.** Every table carries `org_id` and every query filters on it. A test walks the routes and fails if any `/api` route does not require authentication.

**Sandboxed report templates.** A `.docx` template is Jinja code. Templates uploaded through the portal are rendered in an environment that blocks access to Python internals and escapes values.

**Fail early.** In production the app refuses to start with the default session key. The database connection has a timeout, so the health check answers even when the database does not. Uploads are read in chunks and rejected as soon as they pass the size limit, instead of being loaded whole into memory first.

**Progress by notification, not polling.** Each progress event issues a `NOTIFY` in the same transaction that stores it. The API keeps one `LISTEN` connection per process and wakes only the SSE connections of the notified organization. The notification carries no data: the events table remains the source, so a lost notification costs a delay, not an event. If the `LISTEN` connection drops, the stream falls back to short-interval polling until it is back.

**Migrations as the schema's source of truth.** An integration test compares what the ORM models declare with what the migrations create on an empty Postgres (tables, columns, types, keys and indexes) and fails if they diverge. When it was written it found indexes declared one way in the models and created another way in the migrations; the models were aligned.

## Tests

```bash
# Backend: lint and unit tests (no database, network or API key)
cd backend
ruff check .
pytest

# Backend: integration tests, on the docker compose Postgres
docker compose exec db createdb -U postgres rma_teste
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/rma_teste \
  RMA_TESTE_INTEGRACAO=1 pytest -m integracao

# Frontend
cd ../frontend
npm run lint && npm run typecheck && npm test
```

**Unit (68 tests).** In-memory SQLite and fakes for storage, e-mail and AI. They cover category normalization, JSON repair, persistence and deduplication, the indicator engine, group consolidation, report assembly, the security rules, size-limited upload reading and the event bus behind live progress.

**Integration (12 tests).** The API on a real Postgres, with the schema created by the migrations and by Procrastinate, as in production. They cover migrations up to the latest revision, models versus migrations, the upload → queued job → pipeline → indicators path, a real income statement replacing the one derived from the trial balance, deduplication on re-upload, cascading deletes through foreign keys, a report from request to download, isolation between organizations, and `NOTIFY` waking the stream. They only run on request and against a database whose name ends in `_teste`, because they empty the tables on every test.

**Frontend (23 tests).** Vitest on the pure formatting, search and sorting functions. ESLint (recommended, TypeScript and hooks rules) and `tsc` complete the checks.

CI runs all of it on every push, in four jobs: backend, integration (with a Postgres 16 service), frontend and the Docker image build.

## Known limitations

- In practice there is a single organization, created from the configured name at first login. Isolation by `org_id` exists and is tested, but there is no organization sign-up or administration.
- Integration tests do not start the worker or call the AI: the queued job is checked in the queue table and run inline, and AI and storage are fakes. Extraction quality depends on the model and is not measured by an automated test.
- React components have no tests; only the pure functions do. The larger components concentrate state and API calls.
- `LISTEN/NOTIFY` covers document progress. The reports screen still polls the list every 4 s while it is open.
- The recorded AI cost is an estimate from a configurable price table, not the billed amount.
- Frontend dependencies are at the versions the project was built with (React 18, Vite 5).

## Author

Filipe Dias Brandão · [github.com/FIlIpeDiBr](https://github.com/FIlIpeDiBr)

Published as a portfolio piece. All rights reserved.
