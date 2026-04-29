import json
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .jira_client import find_issue, log_work
from .parser import parse_worklog
from .stt import get_model, transcribe
from .worklog import get_entries, save_entry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Loading Whisper model (first run may take a few minutes to download)...")
    get_model()
    log.info("Whisper model ready.")
    yield


app = FastAPI(title="Vinnie Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="/frontend"), name="static")


@app.get("/")
async def index():
    return FileResponse("/frontend/index.html")


@app.post("/process")
async def process(
    file: UploadFile = File(...),
    context: str = Form(default=""),
):
    audio_bytes = await file.read()
    log.info("Received audio: %d bytes", len(audio_bytes))

    text = transcribe(audio_bytes)
    log.info("Transcribed: %s", text)

    # Убираем стоп-фразу из транскрипции перед парсингом
    text = re.sub(r"\s*конец записи\.?\s*$", "", text, flags=re.IGNORECASE).strip()

    if not text:
        return JSONResponse({"status": "error", "voice_message": "Не расслышал. Попробуй ещё раз."})

    ctx = json.loads(context) if context else None

    try:
        parsed = parse_worklog(text, context=ctx)
    except Exception as e:
        log.error("Parse error: %s", e)
        return JSONResponse({"status": "error", "voice_message": "Не удалось разобрать команду. Попробуй ещё раз."})

    log.info("Parsed: %s", parsed)

    if parsed.get("needs_clarification"):
        merged_ctx = {**(ctx or {}), **{
            k: v for k, v in parsed.items()
            if k in ("task", "time_spent", "date", "description") and v
        }}
        return JSONResponse({
            "status": "clarification",
            "voice_message": parsed["question"],
            "context": merged_ctx,
        })

    task = parsed.get("task") or "—"
    date = parsed.get("date") or ""
    time_spent = parsed.get("time_spent") or "—"
    description = parsed.get("description") or ""

    entry_id = save_entry(task=task, date=date, time_spent=time_spent, description=description)
    log.info("Saved entry #%d", entry_id)

    # Jira: best-effort, не блокирует сохранение в Excel
    jira_status = "skipped"
    if task != "—":
        issue_summary = find_issue(task)
        if issue_summary is None:
            jira_status = "not_found"
            voice_message = f"Записал, но задача {task} не найдена в Jira."
        else:
            ok = log_work(task, time_spent, date, description)
            if ok:
                jira_status = "ok"
                voice_message = "Записал и залогировал в Jira."
            else:
                jira_status = "error"
                voice_message = "Записал в файл, но не удалось залогировать в Jira."
    else:
        voice_message = "Запись успешно сохранена в файл."

    log.info("Jira status: %s", jira_status)

    return JSONResponse({
        "status": "success",
        "voice_message": voice_message,
        "jira_status": jira_status,
        "id": entry_id,
        "transcribed": text,
        "parsed": parsed,
    })


@app.get("/entries")
async def entries():
    return get_entries()
