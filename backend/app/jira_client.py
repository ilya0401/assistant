import logging
from datetime import datetime

import requests

from .config import settings

log = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.jira_api_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _base_url() -> str:
    return settings.jira_url.rstrip("/")


def find_issue(task_key: str) -> str | None:
    """Returns issue summary if found, None if not found or Jira not configured."""
    if not settings.jira_url or not settings.jira_api_token:
        return None
    url = f"{_base_url()}/rest/api/2/issue/{task_key}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=5, verify=False)
        if resp.status_code == 200:
            return resp.json().get("fields", {}).get("summary", "")
        log.warning("Jira find_issue %s: HTTP %d", task_key, resp.status_code)
        return None
    except Exception as e:
        log.error("Jira find_issue error: %s", e)
        return None


def log_work(task_key: str, time_spent: str, date: str, description: str) -> bool:
    """Logs work to Jira issue worklog. Returns True on success."""
    if not settings.jira_url or not settings.jira_api_token:
        return False
    url = f"{_base_url()}/rest/api/2/issue/{task_key}/worklog"
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        started = dt.strftime("%Y-%m-%dT09:00:00.000+0000")
    except (ValueError, TypeError):
        started = datetime.now().strftime("%Y-%m-%dT09:00:00.000+0000")

    payload = {
        "timeSpent": time_spent,
        "started": started,
        "comment": description or "",
    }
    try:
        resp = requests.post(url, headers=_headers(), json=payload, timeout=5, verify=False)
        if resp.status_code in (200, 201):
            return True
        log.warning("Jira log_work %s: HTTP %d — %s", task_key, resp.status_code, resp.text[:200])
        return False
    except Exception as e:
        log.error("Jira log_work error: %s", e)
        return False