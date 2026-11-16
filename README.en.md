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

**Auditable AI cost.** Every model call stores model, tokens, estimated cost, duration, prompt and response in the `ai_calls` table.

**Indicators as data.** The 23 definitions live in a table and each organization can override a formula without touching code. Formulas go through a purpose-built evaluator, no `eval`.

**Human review for e-mail intake.** The mailbox is polled every 5 minutes, but no attachment enters the pipeline until someone approves it.

**Isolation per organization.** Every table carries `org_id` and every query filters on it. A test walks the routes and fails if any `/api` route does not require authentication.

**Sandboxed report templates.** A `.docx` template is Jinja code. Templates uploaded through the portal are rendered in an environment that blocks access to Python internals and escapes values.

**Fail early on configuration.** In production the app refuses to start with the default session key. The database connection has a timeout, so the health check answers even when the database does not.

## Tests

```bash
cd backend
ruff check .
pytest
```

The 49 tests run without a database, network or API key: in-memory SQLite and fakes for storage, e-mail and AI. CI runs lint, tests, the frontend build and the Docker image build.

## Known limitations

- The frontend has no tests or lint.
- Live progress polls the database every 1.5 s per connection; Postgres `LISTEN/NOTIFY` would avoid that.
- Upload reads the whole file into memory before checking the size limit.
- In practice there is a single organization, created from the configured name at first login.
- API tests cover authentication and health only; full flows against a real database are not automated.

## Author

Filipe Dias Brandão · [github.com/FIlIpeDiBr](https://github.com/FIlIpeDiBr)

Published as a portfolio piece. All rights reserved.
