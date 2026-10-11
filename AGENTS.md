# Papaia Misc

- Preserve the React/Vite + FastAPI monorepo and provider interfaces.
- Read `docs/architecture.md` before schema or collection changes.
- No invented external records, audience metrics, verified credentials, or private contacts.
- Keep credentials in backend environment variables; never expose them to browser code or logs.
- Sources must retain URLs and provenance. Show collection failures and pending integrations.
- Score evidence and missing metrics must remain explicit. Followers alone must not increase scores.
- Contact proposals are drafts; no automatic sending.
- All `/api` commercial data endpoints require authentication; public health contains no records.
- Use Alembic for schema changes; index foreign keys and preserve database constraints.
- Run `backend/.venv/bin/pytest backend/tests -q`, `npm test --prefix frontend`, and `npm run build --prefix frontend` after relevant changes.
- PostgreSQL CI uses `TEST_DATABASE_URL`; never point it to a database with valuable data: tests drop tables.
- Validate public URLs and pin DNS before every external fetch. Never weaken SSRF checks to bypass an inaccessible source.
- Do not enable demos or provider credentials automatically.
