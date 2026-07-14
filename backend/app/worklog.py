from datetime import date as date_cls

import psycopg

from .config import settings

TABLE_NAME = "worklog_entries"


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id          SERIAL PRIMARY KEY,
                task        TEXT NOT NULL,
                entry_date  DATE NOT NULL,
                time_spent  TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                added_at    TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


def _row_to_dict(row) -> dict:
    id_, task, entry_date, time_spent, description, added_at = row
    return {
        "id": id_,
        "task": task,
        "date": entry_date.isoformat() if entry_date else "",
        "time_spent": time_spent,
        "description": description,
        "added": added_at.strftime("%Y-%m-%d %H:%M") if added_at else "",
    }


def save_entry(task: str, date: str, time_spent: str, description: str) -> int:
    entry_date = date_cls.fromisoformat(date)
    with get_connection() as conn:
        cur = conn.execute(
            f"INSERT INTO {TABLE_NAME} (task, entry_date, time_spent, description) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (task, entry_date, time_spent, description),
        )
        return cur.fetchone()[0]


def get_entry_by_id(entry_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT id, task, entry_date, time_spent, description, added_at "
            f"FROM {TABLE_NAME} WHERE id = %s",
            (entry_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_entries(limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, task, entry_date, time_spent, description, added_at "
            f"FROM {TABLE_NAME} ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
