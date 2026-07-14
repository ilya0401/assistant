import json
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .jira_client import find_issue, jira_configured, log_work
from .parser import parse_task_only, parse_worklog
from .stt import get_model, transcribe
from .worklog import get_entries, get_entry_by_id, init_db, save_entry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("Postgres table ready.")
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
    task_prefix: str = Form(default=""),
    task_only: str = Form(default=""),
):
    audio_bytes = await file.read(10 * 1024 * 1024)  # max 10 MB
    if len(audio_bytes) >= 10 * 1024 * 1024:
        return JSONResponse({"status": "error", "voice_message": "Файл слишком большой. Максимум 10 МБ."})
    log.info("Received audio: %d bytes", len(audio_bytes))

    text = transcribe(audio_bytes)
    log.info("Transcribed: %s", text)

    text = re.sub(r"\s*конец записи\.?\s*$", "", text, flags=re.IGNORECASE).strip()

    if not text:
        return JSONResponse({"status": "error", "voice_message": "Не расслышал. Попробуй ещё раз."})

    # Режим перезаписи только номера задачи
    if task_only:
        task = parse_task_only(text, task_prefix)
        if not task:
            return JSONResponse({"status": "error", "voice_message": "Не расслышал цифры. Попробуй ещё раз."})
        log.info("Task-only result: %s", task)
        return JSONResponse({"status": "task_only_result", "task": task})

    ctx = json.loads(context) if context else None

    try:
        parsed = parse_worklog(text, context=ctx, task_prefix=task_prefix)
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

    # Все поля заполнены — возвращаем на подтверждение номера задачи (не сохраняем)
    task = parsed.get("task") or "—"
    return JSONResponse({
        "status": "task_confirmation",
        "voice_message": f"Правильно ли я записал номер задачи {task}?",
        "parsed": parsed,
        "transcribed": text,
    })


@app.post("/confirm")
async def confirm(request: Request):
    data = await request.json()
    task = data.get("task") or "—"
    date = data.get("date") or ""
    time_spent = data.get("time_spent") or "—"
    description = data.get("description") or ""
    transcribed = data.get("transcribed") or ""

    try:
        entry_id = save_entry(task=task, date=date, time_spent=time_spent, description=description)
    except ValueError:
        return JSONResponse({
            "status": "error",
            "voice_message": "Некорректная дата. Используй формат ГГГГ-ММ-ДД, например 2026-07-14.",
        })
    log.info("Confirmed and saved entry #%d", entry_id)

    jira_status = "skipped"
    voice_message = "Запись успешно сохранена в файл."
    if task != "—" and jira_configured():
        if not description.strip():
            jira_status = "error"
            voice_message = "Записал в файл, но не залогировал в Jira: не указано описание."
        else:
            try:
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
            except Exception as e:
                log.error("Jira error: %s", e)
                jira_status = "error"
                voice_message = "Записал в файл, но не удалось подключиться к Jira."

    log.info("Jira status: %s", jira_status)

    return JSONResponse({
        "status": "success",
        "voice_message": voice_message,
        "jira_status": jira_status,
        "id": entry_id,
        "transcribed": transcribed,
        "parsed": data,
    })


@app.get("/jira-test/{task_key}")
async def jira_test(task_key: str):
    import requests as _req
    from .jira_client import _auth, _base_url, _headers, _get_token
    configured = jira_configured()
    if not configured:
        return JSONResponse({"configured": False, "jira_url": settings.jira_url,
                             "jira_email": settings.jira_email, "has_token": bool(_get_token())})
    url = f"{_base_url()}/rest/api/3/issue/{task_key}"
    try:
        resp = _req.get(url, headers=_headers(), auth=_auth(), timeout=10)
        return JSONResponse({"configured": True, "url": url, "status": resp.status_code,
                             "email": settings.jira_email,
                             "body_preview": resp.text[:300]})
    except Exception as e:
        return JSONResponse({"configured": True, "url": url, "error": str(e)})


@app.get("/entries/{entry_id}")
async def entry_by_id(entry_id: int):
    entry = get_entry_by_id(entry_id)
    if entry is None:
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return entry


@app.get("/entries")
async def entries():
    return get_entries()
