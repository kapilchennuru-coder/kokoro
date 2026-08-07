# SQLite helper for the AI calling dashboard.
# Keeps legacy patients table for compatibility; new UI uses contacts/campaigns.

import json
import os
import sqlite3
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

CREATE TABLE IF NOT EXISTS contact_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    filename TEXT,
    mapping_json TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    valid_count INTEGER NOT NULL DEFAULT 0,
    invalid_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    list_id INTEGER,
    name TEXT NOT NULL DEFAULT '',
    first_name TEXT,
    last_name TEXT,
    phone TEXT,
    email TEXT,
    company TEXT,
    location TEXT,
    notes TEXT,
    extras_json TEXT,
    validation_status TEXT NOT NULL DEFAULT 'valid',
    validation_errors TEXT,
    calling_status TEXT NOT NULL DEFAULT 'not_called',
    last_called_at TEXT,
    last_campaign_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    balance REAL,
    hospital TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (list_id) REFERENCES contact_lists (id)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    list_id INTEGER,
    voice_id TEXT NOT NULL DEFAULT 'af_jessica',
    voice_speed REAL NOT NULL DEFAULT 1.0,
    agent_name TEXT NOT NULL DEFAULT 'Sales Outreach Agent',
    opening_message TEXT,
    calling_mode TEXT NOT NULL DEFAULT 'sequential',
    max_calls INTEGER,
    delay_ms INTEGER NOT NULL DEFAULT 2000,
    concurrency INTEGER NOT NULL DEFAULT 1,
    total_contacts INTEGER NOT NULL DEFAULT 0,
    completed_calls INTEGER NOT NULL DEFAULT 0,
    successful_calls INTEGER NOT NULL DEFAULT 0,
    no_answer_calls INTEGER NOT NULL DEFAULT 0,
    failed_calls INTEGER NOT NULL DEFAULT 0,
    in_progress_calls INTEGER NOT NULL DEFAULT 0,
    current_contact_id INTEGER,
    current_call_id INTEGER,
    agent_state TEXT NOT NULL DEFAULT 'idle',
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (list_id) REFERENCES contact_lists (id)
);

CREATE TABLE IF NOT EXISTS campaign_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    contact_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    call_id INTEGER,
    FOREIGN KEY (campaign_id) REFERENCES campaigns (id),
    FOREIGN KEY (contact_id) REFERENCES contacts (id)
);

CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    campaign_id INTEGER,
    contact_id INTEGER,
    status TEXT NOT NULL DEFAULT 'in_progress',
    outcome TEXT,
    duration_sec INTEGER DEFAULT 0,
    script_text TEXT,
    transcript_json TEXT,
    events_json TEXT,
    detail TEXT,
    audio_filename TEXT,
    started_at TEXT,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns (id),
    FOREIGN KEY (contact_id) REFERENCES contacts (id)
);

CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (user_id, key),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


def _ensure_column(conn, table: str, column: str, typedef: str):
    cols = set()
    for row in conn.execute(f"PRAGMA table_info({table})").fetchall():
        name = row["name"] if isinstance(row, sqlite3.Row) else row[1]
        cols.add(str(name))
    if column in cols:
        return
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")
    except sqlite3.OperationalError as exc:
        # Safe if a concurrent process already added the column
        if "duplicate column" not in str(exc).lower():
            raise


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _ensure_column(conn, "contacts", "balance", "REAL")
        _ensure_column(conn, "contacts", "hospital", "TEXT")
        # Seed demo user if none exist
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if count == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash, client_name, created_at) VALUES (?, ?, ?, ?)",
                ("demo", generate_password_hash("demo123"), "Outreach", now_iso()),
            )


def create_user(username: str, password: str, client_name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, client_name, created_at) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), client_name, now_iso()),
        )


def get_user_by_username(username: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


# ---- Legacy patients (preserved) ----

def replace_patients(user_id: int, patients: list):
    now = now_iso()
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
            (status, detail, now_iso(), row_id),
        )


# ---- Contact lists ----

def create_contact_list(user_id: int, name: str, filename: str, mapping: dict, row_count: int, valid_count: int, invalid_count: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO contact_lists
               (user_id, name, filename, mapping_json, row_count, valid_count, invalid_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, name, filename, json.dumps(mapping), row_count, valid_count, invalid_count, now_iso()),
        )
        return cur.lastrowid


def get_contact_lists(user_id: int):
    with get_conn() as conn:
        return rows_to_list(
            conn.execute(
                "SELECT * FROM contact_lists WHERE user_id = ? ORDER BY id DESC", (user_id,)
            ).fetchall()
        )


def get_contact_list(user_id: int, list_id: int):
    with get_conn() as conn:
        return row_to_dict(
            conn.execute(
                "SELECT * FROM contact_lists WHERE user_id = ? AND id = ?", (user_id, list_id)
            ).fetchone()
        )


def update_contact_list_counts(list_id: int, row_count: int, valid_count: int, invalid_count: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE contact_lists SET row_count = ?, valid_count = ?, invalid_count = ? WHERE id = ?",
            (row_count, valid_count, invalid_count, list_id),
        )


# ---- Contacts ----

def _enrich_patient(item: dict) -> dict:
    """Normalize contact row into patient-facing fields."""
    if not item:
        return item
    extras = item.get("extras")
    if extras is None:
        extras = json.loads(item.get("extras_json") or "{}")
        item["extras"] = extras
    balance = item.get("balance")
    if balance is None and extras.get("balance") is not None:
        try:
            balance = float(extras["balance"])
        except (TypeError, ValueError):
            balance = None
    hospital = item.get("hospital") or item.get("company") or extras.get("hospital") or ""
    item["balance"] = balance
    item["hospital"] = hospital
    item["balance_display"] = f"${float(balance):,.2f}" if balance is not None else "—"
    return item


def insert_contacts(user_id: int, list_id: int, contacts: list) -> list:
    now = now_iso()
    ids = []
    with get_conn() as conn:
        for c in contacts:
            hospital = c.get("hospital") or c.get("company") or ""
            balance = c.get("balance")
            cur = conn.execute(
                """INSERT INTO contacts
                   (user_id, list_id, name, first_name, last_name, phone, email, company, location, notes,
                    extras_json, validation_status, validation_errors, calling_status, created_at, updated_at,
                    balance, hospital)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_called', ?, ?, ?, ?)""",
                (
                    user_id,
                    list_id,
                    c.get("name") or "",
                    c.get("first_name"),
                    c.get("last_name"),
                    c.get("phone"),
                    None,
                    hospital,
                    None,
                    None,
                    json.dumps({"balance": balance, "hospital": hospital}),
                    c.get("validation_status", "valid"),
                    json.dumps(c.get("validation_errors") or []),
                    now,
                    now,
                    balance,
                    hospital,
                ),
            )
            ids.append(cur.lastrowid)
    return ids


def get_contacts(
    user_id: int,
    *,
    list_id: int | None = None,
    search: str = "",
    status: str = "",
    validation: str = "",
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "id",
    sort_dir: str = "asc",
):
    allowed_sort = {"id", "name", "phone", "company", "email", "calling_status", "created_at", "validation_status"}
    if sort_by not in allowed_sort:
        sort_by = "id"
    sort_dir = "DESC" if sort_dir.lower() == "desc" else "ASC"

    clauses = ["user_id = ?"]
    params: list = [user_id]
    if list_id:
        clauses.append("list_id = ?")
        params.append(list_id)
    if search:
        clauses.append("(name LIKE ? OR phone LIKE ? OR company LIKE ? OR hospital LIKE ?)")
        q = f"%{search}%"
        params.extend([q, q, q, q])
    if status:
        clauses.append("calling_status = ?")
        params.append(status)
    if validation:
        clauses.append("validation_status = ?")
        params.append(validation)

    where = " AND ".join(clauses)
    offset = max(page - 1, 0) * page_size

    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM contacts WHERE {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM contacts WHERE {where} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
        items = rows_to_list(rows)
        for item in items:
            item["validation_errors"] = json.loads(item.get("validation_errors") or "[]")
            item["extras"] = json.loads(item.get("extras_json") or "{}")
            _enrich_patient(item)
        return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_contact(user_id: int, contact_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM contacts WHERE user_id = ? AND id = ?", (user_id, contact_id)
        ).fetchone()
        item = row_to_dict(row)
        if item:
            item["validation_errors"] = json.loads(item.get("validation_errors") or "[]")
            item["extras"] = json.loads(item.get("extras_json") or "{}")
            _enrich_patient(item)
        return item


def get_valid_contacts_for_list(user_id: int, list_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM contacts
               WHERE user_id = ? AND list_id = ? AND validation_status = 'valid'
               ORDER BY id""",
            (user_id, list_id),
        ).fetchall()
        items = rows_to_list(rows)
        for item in items:
            item["validation_errors"] = json.loads(item.get("validation_errors") or "[]")
            item["extras"] = json.loads(item.get("extras_json") or "{}")
            _enrich_patient(item)
        return items


def get_ready_contacts(user_id: int):
    """All valid patients ready to call (not_called)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM contacts
               WHERE user_id = ? AND validation_status = 'valid'
                 AND calling_status IN ('not_called', 'failed', 'no_answer')
               ORDER BY id""",
            (user_id,),
        ).fetchall()
        items = rows_to_list(rows)
        for item in items:
            item["validation_errors"] = json.loads(item.get("validation_errors") or "[]")
            item["extras"] = json.loads(item.get("extras_json") or "{}")
            _enrich_patient(item)
        return items


def update_contact(user_id: int, contact_id: int, data: dict) -> dict | None:
    existing = get_contact(user_id, contact_id)
    if not existing:
        return None
    name = data.get("name", existing["name"])
    phone = data.get("phone", existing["phone"])
    balance = data.get("balance", existing.get("balance"))
    hospital = data.get("hospital", existing.get("hospital") or "")
    try:
        balance = float(balance) if balance is not None and balance != "" else None
    except (TypeError, ValueError):
        balance = existing.get("balance")
    with get_conn() as conn:
        conn.execute(
            """UPDATE contacts
               SET name = ?, phone = ?, balance = ?, hospital = ?, company = ?,
                   extras_json = ?, updated_at = ?
               WHERE user_id = ? AND id = ?""",
            (
                name,
                phone,
                balance,
                hospital,
                hospital,
                json.dumps({"balance": balance, "hospital": hospital}),
                now_iso(),
                user_id,
                contact_id,
            ),
        )
    return get_contact(user_id, contact_id)


def delete_contact(user_id: int, contact_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM contacts WHERE user_id = ? AND id = ?",
            (user_id, contact_id),
        )
        return cur.rowcount > 0


def count_contacts(user_id: int) -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM contacts WHERE user_id = ?", (user_id,)).fetchone()["c"]
        valid = conn.execute(
            "SELECT COUNT(*) AS c FROM contacts WHERE user_id = ? AND validation_status = 'valid'",
            (user_id,),
        ).fetchone()["c"]
        ready = conn.execute(
            """SELECT COUNT(*) AS c FROM contacts
               WHERE user_id = ? AND validation_status = 'valid'
                 AND calling_status IN ('not_called', 'failed', 'no_answer')""",
            (user_id,),
        ).fetchone()["c"]
        in_progress = conn.execute(
            "SELECT COUNT(*) AS c FROM contacts WHERE user_id = ? AND calling_status = 'in_progress'",
            (user_id,),
        ).fetchone()["c"]
        completed = conn.execute(
            "SELECT COUNT(*) AS c FROM contacts WHERE user_id = ? AND calling_status = 'completed'",
            (user_id,),
        ).fetchone()["c"]
        return {
            "total": total,
            "valid": valid,
            "ready": ready,
            "in_progress": in_progress,
            "completed": completed,
            "remaining": max(total - completed, 0),
            "invalid": total - valid,
        }


def update_contact_calling(contact_id: int, status: str, campaign_id: int | None = None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE contacts SET calling_status = ?, last_called_at = ?, last_campaign_id = COALESCE(?, last_campaign_id), updated_at = ?
               WHERE id = ?""",
            (status, now_iso(), campaign_id, now_iso(), contact_id),
        )


# ---- Campaigns ----

def create_campaign(user_id: int, data: dict) -> int:
    now = now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO campaigns
               (user_id, name, status, list_id, voice_id, voice_speed, agent_name, opening_message,
                calling_mode, max_calls, delay_ms, concurrency, total_contacts, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                data["name"],
                data.get("status", "draft"),
                data.get("list_id"),
                data.get("voice_id", "af_jessica"),
                data.get("voice_speed", 1.0),
                data.get("agent_name", "Sales Outreach Agent"),
                data.get("opening_message"),
                data.get("calling_mode", "sequential"),
                data.get("max_calls"),
                data.get("delay_ms", 2000),
                data.get("concurrency", 1),
                data.get("total_contacts", 0),
                now,
                now,
            ),
        )
        return cur.lastrowid


def link_campaign_contacts(campaign_id: int, contact_ids: list):
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO campaign_contacts (campaign_id, contact_id, status) VALUES (?, ?, 'pending')",
            [(campaign_id, cid) for cid in contact_ids],
        )


def get_campaigns(user_id: int):
    with get_conn() as conn:
        return rows_to_list(
            conn.execute(
                "SELECT * FROM campaigns WHERE user_id = ? ORDER BY id DESC", (user_id,)
            ).fetchall()
        )


def get_campaign(user_id: int, campaign_id: int):
    with get_conn() as conn:
        return row_to_dict(
            conn.execute(
                "SELECT * FROM campaigns WHERE user_id = ? AND id = ?", (user_id, campaign_id)
            ).fetchone()
        )


def get_campaign_by_id(campaign_id: int):
    with get_conn() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        )


def update_campaign(campaign_id: int, **fields):
    if not fields:
        return
    fields["updated_at"] = now_iso()
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [campaign_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE campaigns SET {cols} WHERE id = ?", vals)


def get_pending_campaign_contacts(campaign_id: int):
    with get_conn() as conn:
        return rows_to_list(
            conn.execute(
                """SELECT cc.*, c.name, c.phone, c.email, c.company, c.location, c.notes, c.first_name, c.last_name
                   FROM campaign_contacts cc
                   JOIN contacts c ON c.id = cc.contact_id
                   WHERE cc.campaign_id = ? AND cc.status = 'pending'
                   ORDER BY cc.id""",
                (campaign_id,),
            ).fetchall()
        )


def update_campaign_contact(campaign_id: int, contact_id: int, status: str, call_id: int | None = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE campaign_contacts SET status = ?, call_id = COALESCE(?, call_id) WHERE campaign_id = ? AND contact_id = ?",
            (status, call_id, campaign_id, contact_id),
        )


def get_active_campaign(user_id: int):
    with get_conn() as conn:
        return row_to_dict(
            conn.execute(
                """SELECT * FROM campaigns
                   WHERE user_id = ? AND status IN ('running', 'paused')
                   ORDER BY updated_at DESC LIMIT 1""",
                (user_id,),
            ).fetchone()
        )


# ---- Calls ----

def create_call(user_id: int, campaign_id: int, contact_id: int, script_text: str) -> int:
    now = now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO calls
               (user_id, campaign_id, contact_id, status, script_text, transcript_json, events_json, started_at, created_at)
               VALUES (?, ?, ?, 'in_progress', ?, ?, ?, ?, ?)""",
            (user_id, campaign_id, contact_id, script_text, "[]", "[]", now, now),
        )
        return cur.lastrowid


def update_call(call_id: int, **fields):
    if not fields:
        return
    # Serialize JSON fields if passed as objects
    for key in ("transcript_json", "events_json"):
        if key in fields and not isinstance(fields[key], str):
            fields[key] = json.dumps(fields[key])
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [call_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE calls SET {cols} WHERE id = ?", vals)


def append_call_event(call_id: int, event: dict):
    with get_conn() as conn:
        row = conn.execute("SELECT events_json FROM calls WHERE id = ?", (call_id,)).fetchone()
        events = json.loads(row["events_json"] or "[]") if row else []
        events.append(event)
        conn.execute("UPDATE calls SET events_json = ? WHERE id = ?", (json.dumps(events), call_id))


def append_transcript(call_id: int, entry: dict):
    with get_conn() as conn:
        row = conn.execute("SELECT transcript_json FROM calls WHERE id = ?", (call_id,)).fetchone()
        items = json.loads(row["transcript_json"] or "[]") if row else []
        items.append(entry)
        conn.execute("UPDATE calls SET transcript_json = ? WHERE id = ?", (json.dumps(items), call_id))


def get_calls(
    user_id: int,
    *,
    search: str = "",
    status: str = "",
    campaign_id: int | None = None,
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 25,
):
    clauses = ["calls.user_id = ?"]
    params: list = [user_id]
    if search:
        clauses.append("(contacts.name LIKE ? OR contacts.phone LIKE ? OR campaigns.name LIKE ?)")
        q = f"%{search}%"
        params.extend([q, q, q])
    if status:
        clauses.append("calls.status = ?")
        params.append(status)
    if campaign_id:
        clauses.append("calls.campaign_id = ?")
        params.append(campaign_id)
    if date_from:
        clauses.append("calls.created_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("calls.created_at <= ?")
        params.append(date_to)

    where = " AND ".join(clauses)
    offset = max(page - 1, 0) * page_size

    with get_conn() as conn:
        total = conn.execute(
            f"""SELECT COUNT(*) AS c FROM calls
                LEFT JOIN contacts ON contacts.id = calls.contact_id
                LEFT JOIN campaigns ON campaigns.id = calls.campaign_id
                WHERE {where}""",
            params,
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT calls.*, contacts.name AS contact_name, contacts.phone AS contact_phone,
                       contacts.company AS contact_company, contacts.hospital AS hospital,
                       contacts.balance AS balance, campaigns.name AS campaign_name
                FROM calls
                LEFT JOIN contacts ON contacts.id = calls.contact_id
                LEFT JOIN campaigns ON campaigns.id = calls.campaign_id
                WHERE {where}
                ORDER BY calls.id DESC
                LIMIT ? OFFSET ?""",
            [*params, page_size, offset],
        ).fetchall()
        items = rows_to_list(rows)
        for item in items:
            item["transcript"] = json.loads(item.get("transcript_json") or "[]")
            item["events"] = json.loads(item.get("events_json") or "[]")
            if item.get("balance") is not None:
                try:
                    item["balance_display"] = f"${float(item['balance']):,.2f}"
                except (TypeError, ValueError):
                    item["balance_display"] = "—"
            else:
                item["balance_display"] = "—"
            item["hospital"] = item.get("hospital") or item.get("contact_company") or "—"
        return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_call(user_id: int, call_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT calls.*, contacts.name AS contact_name, contacts.phone AS contact_phone,
                      contacts.email AS contact_email, contacts.company AS contact_company,
                      campaigns.name AS campaign_name
               FROM calls
               LEFT JOIN contacts ON contacts.id = calls.contact_id
               LEFT JOIN campaigns ON campaigns.id = calls.campaign_id
               WHERE calls.user_id = ? AND calls.id = ?""",
            (user_id, call_id),
        ).fetchone()
        item = row_to_dict(row)
        if item:
            item["transcript"] = json.loads(item.get("transcript_json") or "[]")
            item["events"] = json.loads(item.get("events_json") or "[]")
        return item


def count_calls(user_id: int) -> dict:
    with get_conn() as conn:
        completed = conn.execute(
            "SELECT COUNT(*) AS c FROM calls WHERE user_id = ? AND status = 'completed'",
            (user_id,),
        ).fetchone()["c"]
        answered = conn.execute(
            "SELECT COUNT(*) AS c FROM calls WHERE user_id = ? AND outcome = 'answered'",
            (user_id,),
        ).fetchone()["c"]
        return {"completed": completed, "answered": answered}


# ---- Settings & notifications ----

DEFAULT_SETTINGS = {
    "voice_id": "af_jessica",
    "voice_speed": "1.0",
    "agent_name": "Outreach",
    "opening_message": (
        "Hello {name}, this is a courtesy call from {hospital}. "
        "Our records show you have a pending balance of {balance_display}. "
        "Please contact the billing office at your earliest convenience. Thank you."
    ),
    "calling_mode": "sequential",
    "max_calls": "100",
    "delay_ms": "2000",
    "concurrency": "1",
}


def get_settings(user_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings WHERE user_id = ?", (user_id,)).fetchall()
    settings = dict(DEFAULT_SETTINGS)
    for r in rows:
        settings[r["key"]] = r["value"]
    return settings


def save_settings(user_id: int, data: dict):
    with get_conn() as conn:
        for key, value in data.items():
            conn.execute(
                """INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)
                   ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value""",
                (user_id, key, str(value)),
            )


def add_notification(user_id: int, message: str, level: str = "info"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notifications (user_id, message, level, created_at) VALUES (?, ?, ?, ?)",
            (user_id, message, level, now_iso()),
        )


def get_notifications(user_id: int, limit: int = 20):
    with get_conn() as conn:
        return rows_to_list(
            conn.execute(
                "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        )


def mark_notifications_read(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE notifications SET read = 1 WHERE user_id = ?", (user_id,))
