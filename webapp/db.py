# SQLite helper for the calling-agent web app.
# Single file DB, fine for the free-tier hosting target - upgrade to
# Postgres later if a client needs more than light demo volume.

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    client_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    patient_id TEXT NOT NULL,
    patient_name TEXT NOT NULL,
    phone_number TEXT,
    balance_amount REAL,
    call_status TEXT NOT NULL DEFAULT 'not_called',
    call_detail TEXT,
    last_called_at TEXT,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def create_user(username: str, password: str, client_name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, client_name, created_at) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), client_name, datetime.now(timezone.utc).isoformat()),
        )


def get_user_by_username(username: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def replace_patients(user_id: int, patients: list):
    """Wipes this client's previous patient list and inserts the newly uploaded one."""
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute("DELETE FROM patients WHERE user_id = ?", (user_id,))
        conn.executemany(
            """INSERT INTO patients
               (user_id, patient_id, patient_name, phone_number, balance_amount, call_status, uploaded_at)
               VALUES (?, ?, ?, ?, ?, 'not_called', ?)""",
            [
                (user_id, p["patient_id"], p["patient_name"], p.get("phone_number"), p["balance_amount"], now)
                for p in patients
            ],
        )


def get_patients(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM patients WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()


def get_patient(user_id: int, row_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM patients WHERE user_id = ? AND id = ?", (user_id, row_id)
        ).fetchone()


def update_call_result(row_id: int, status: str, detail: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE patients SET call_status = ?, call_detail = ?, last_called_at = ? WHERE id = ?",
            (status, detail, datetime.now(timezone.utc).isoformat(), row_id),
        )
