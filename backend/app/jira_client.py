import logging
from datetime import datetime, timezone

import requests

from .config import settings

log = logging.getLogger(__name__)


def _get_token() -> str:
    if settings.jira_token_file:
        try:
            return open(settings.jira_token_file).read().strip()
        except OSError as e:
            log.error("Cannot read JIRA_TOKEN_FILE %s: %s", settings.jira_token_file, e)
    return settings.jira_api_token


def _auth() -> tuple[str, str]:
    return (settings.jira_email, _get_token())


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _base_url() -> str:
    return settings.jira_url.rstrip("/")


def jira_configured() -> bool:
    return bool(settings.jira_url and settings.jira_email and _get_token())


def find_issue(task_key: str) -> str | None:
    """Returns issue summary if found, None if not found (404), raises on error."""
    url = f"{_base_url()}/rest/api/3/issue/{task_key}"
    resp = requests.get(url, headers=_headers(), auth=_auth(), timeout=15)
    log.info("Jira find_issue %s: HTTP %d", task_key, resp.status_code)
    if resp.status_code == 200:
        return resp.json().get("fields", {}).get("summary", "")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()


def log_work(task_key: str, time_spent: str, date: str, description: str) -> bool:
    """Logs work to Jira issue worklog. Returns True on success."""
    if not settings.jira_url or not settings.jira_email or not _get_token():
        return False
    url = f"{_base_url()}/rest/api/3/issue/{task_key}/worklog"
    now_utc = datetime.now(tz=timezone.utc)
    today = now_utc.date()
    try:
        dt = datetime.strptime(date, "%Y-%m-%d").date()
        if dt == today:
            started = now_utc.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
        else:
            started = f"{date}T09:00:00.000+0000"
    except (ValueError, TypeError):
        started = now_utc.strftime("%Y-%m-%dT%H:%M:%S.000+0000")

    payload = {
        "timeSpent": time_spent,
        "started": started,
        "comment": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description or ""}]}],
        },
    }
    try:
        resp = requests.post(url, headers=_headers(), auth=_auth(), json=payload, timeout=15)
        if resp.status_code in (200, 201):
            return True
        log.warning("Jira log_work %s: HTTP %d — %s", task_key, resp.status_code, resp.text[:200])
        return False
    except Exception as e:
        log.error("Jira log_work error: %s", e)
        return False