"""One-off migration: import data/worklog.xlsx rows into Postgres.

Run once, from inside the running `vinnie` container, after `docker compose up`:
    docker compose exec vinnie python -m scripts.migrate_xlsx_to_postgres

Idempotent: uses ON CONFLICT (id) DO NOTHING, safe to re-run.
Does not modify or delete the source .xlsx file.
"""
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl

from app.config import settings
from app.worklog import TABLE_NAME, get_connection, init_db


def _parse_added(raw) -> datetime:
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return datetime.now()


def _parse_date(raw, added_at: datetime) -> date:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    s = str(raw or "").strip()
    try:
        return date.fromisoformat(s)
    except ValueError:
        fallback = added_at.date()
        print(f"WARNING: row has unparseable date {s!r}; using added_at date {fallback} instead. Fix later with SQL if needed.")
        return fallback


def main() -> None:
    xlsx_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(settings.data_dir) / "worklog.xlsx"
    if not xlsx_path.exists():
        print(f"No workbook found at {xlsx_path}, nothing to migrate.")
        return

    init_db()

    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] is not None]
    wb.close()
    print(f"Found {len(rows)} rows in {xlsx_path}")

    with get_connection() as conn:
        for entry_id, task, raw_date, time_spent, description, raw_added in rows:
            added_at = _parse_added(raw_added)
            entry_date = _parse_date(raw_date, added_at)
            conn.execute(
                f"INSERT INTO {TABLE_NAME} (id, task, entry_date, time_spent, description, added_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (entry_id, task or "—", entry_date, time_spent or "—", description or "", added_at),
            )
        conn.execute(
            f"SELECT setval(pg_get_serial_sequence('{TABLE_NAME}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {TABLE_NAME}), 1))"
        )

    print(f"Migration complete. Original file left untouched: {xlsx_path}")


if __name__ == "__main__":
    main()
