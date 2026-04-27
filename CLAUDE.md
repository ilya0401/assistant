# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**Vinnie** is a voice-based work time logger. The user speaks into the browser mic, the audio is transcribed via Whisper, structured fields (task ID, time spent, date, description) are extracted, and the result is appended to an Excel worklog. The UI and parsing are Russian-language-first.

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
    worklog.py      openpyxl read/write for /data/worklog.xlsx
    config.py       Pydantic Settings loading from .env
  requirements.txt
  Dockerfile
```

**Request flow**: Browser records WebM → POST `/process` (FormData with audio + optional `context`) → `stt.py` transcribes → `parser.py` extracts fields → if incomplete, returns a clarification prompt (multi-turn loop); if complete, `worklog.py` saves and returns confirmation.

**Persistent data**: `./data/worklog.xlsx` is bind-mounted into the container at `/data/`. The workbook is auto-created with styled Russian-language headers if missing.

## Key Design Decisions

- **No database** — Excel is the only storage.
- **Stateless HTTP** — multi-turn clarification state lives in the browser (accumulated `context` string sent back each turn).
- **Fuzzy matching** (`rapidfuzz`) — compensates for speech recognition errors in Russian keywords.
- **Client-side STT is not used** — the browser sends raw audio to the backend; transcription is always server-side via Whisper.
- **Jira integration** is stubbed in `config.py` but not implemented.
