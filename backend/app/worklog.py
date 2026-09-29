from datetime import date as date_cls

import psycopg

from .config import settings

TABLE_NAME = "worklog_entries"
TASKS_TABLE = "tasks"


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
            CREATE TABLE IF NOT EXISTS {TASKS_TABLE} (
                id       SERIAL PRIMARY KEY,
                task_key TEXT UNIQUE NOT NULL,
                summary  TEXT
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id          SERIAL PRIMARY KEY,
                task_id     INTEGER NOT NULL REFERENCES {TASKS_TABLE}(id),
                entry_date  DATE NOT NULL,
                time_spent  TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                added_at    TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


def _get_or_create_task_id(conn: psycopg.Connection, task_key: str) -> int:
    cur = conn.execute(
        f"INSERT INTO {TASKS_TABLE} (task_key) VALUES (%s) "
        "ON CONFLICT (task_key) DO UPDATE SET task_key = EXCLUDED.task_key "
        "RETURNING id",
        (task_key,),
    )
    return cur.fetchone()[0]


def _row_to_dict(row) -> dict:
    id_, task_key, entry_date, time_spent, description, added_at = row
    return {
        "id": id_,
        "task": task_key,
        "date": entry_date.isoformat() if entry_date else "",
        "time_spent": time_spent,
        "description": description,
        "added": added_at.strftime("%Y-%m-%d %H:%M") if added_at else "",
    }


def save_entry(task: str, date: str, time_spent: str, description: str) -> int:
    entry_date = date_cls.fromisoformat(date)
    with get_connection() as conn:
        task_id = _get_or_create_task_id(conn, task)
        cur = conn.execute(
            f"INSERT INTO {TABLE_NAME} (task_id, entry_date, time_spent, description) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (task_id, entry_date, time_spent, description),
        )
        return cur.fetchone()[0]


def get_entry_by_id(entry_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT we.id, t.task_key, we.entry_date, we.time_spent, we.description, we.added_at "
            f"FROM {TABLE_NAME} we JOIN {TASKS_TABLE} t ON we.task_id = t.id "
            "WHERE we.id = %s",
            (entry_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_entries(limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT we.id, t.task_key, we.entry_date, we.time_spent, we.description, we.added_at "
            f"FROM {TABLE_NAME} we JOIN {TASKS_TABLE} t ON we.task_id = t.id "
            "ORDER BY we.id DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
