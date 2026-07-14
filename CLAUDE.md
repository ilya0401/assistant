# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**Vinnie** is a voice-based work time logger. The user speaks into the browser mic, the audio is transcribed via Whisper, structured fields (task ID, time spent, date, description) are extracted, and the result is stored in Postgres. The UI and parsing are Russian-language-first.

## Running the Project

```bash
# macOS (development)
docker-compose up --build

# Linux / server
docker-compose -f docker-compose.linux.yml up --build -d
docker-compose -f docker-compose.linux.yml logs -f
docker-compose -f docker-compose.linux.yml down
```

Backend runs at `http://localhost:8000`. There is no separate frontend build step — the frontend is static files served by FastAPI from `./frontend/`.

There are no test or lint commands configured.

## Environment Setup

Copy `.env.example` (or create `.env`) with:
- `CLAUDE_API_KEY` — Claude API key (reserved for future use, not actively called today)
- `WHISPER_MODEL` — `tiny` / `base` / `small` / `medium` / `large-v2` (default: `base`)
- `OS_TYPE` — `macos` or `linux`
- `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` — credentials for the `db` service (also consumed directly by the official `postgres` image)

Whisper models are cached in a Docker named volume (`whisper_cache`) so they survive container rebuilds.

## Architecture

```
frontend/           Static SPA (no framework)
  app.js            All client logic: wake-word detection, recording, API calls, UI state
  index.html / style.css

backend/
  app/
    main.py         FastAPI entry point; routes: POST /process, GET /entries, static mount
    stt.py          Loads faster-whisper model once at startup; transcribes uploaded WebM audio
    parser.py       Extracts task/time/date/description using fuzzy keyword matching (rapidfuzz)
    worklog.py      psycopg (raw SQL) read/write against the Postgres `worklog_entries` table
    config.py       Pydantic Settings loading from .env
  scripts/
    migrate_xlsx_to_postgres.py   One-off tool that imports the legacy data/worklog.xlsx into Postgres; already run once, kept for reference
  requirements.txt
  Dockerfile
```

**Request flow**: Browser records WebM → POST `/process` (FormData with audio + optional `context`) → `stt.py` transcribes → `parser.py` extracts fields → if incomplete, returns a clarification prompt (multi-turn loop); if complete, `worklog.py` saves and returns confirmation.

**Persistent data**: worklog entries live in Postgres (`db` service, `worklog_entries` table in the `pgdata` named volume), auto-created on backend startup via `worklog.init_db()`. `./data/worklog.xlsx` remains on disk as a pre-migration historical backup — it is no longer read or written by the app.

## Key Design Decisions

- **Postgres via raw psycopg, no ORM/Alembic** — the `db` service (postgres:16-alpine, separate container) is the source of truth. Schema is a single `CREATE TABLE IF NOT EXISTS` run at startup (`worklog.init_db()`); future schema changes are manual `ALTER TABLE` statements, consistent with this project's minimal-tooling philosophy.
- **Stateless HTTP** — multi-turn clarification state lives in the browser (accumulated `context` string sent back each turn).
- **Fuzzy matching** (`rapidfuzz`) — compensates for speech recognition errors in Russian keywords.
- **Client-side STT is not used** — the browser sends raw audio to the backend; transcription is always server-side via Whisper.
- **Jira integration** is stubbed in `config.py` but not implemented.
