# PostgreSQL data-access layer for the Outreach calling dashboard.
#
# Multi-tenant: contacts/contact_lists/campaigns/calls/settings are scoped
# by organization_id (shared across every user on that team), matching the
# organizations -> {contacts, campaigns, calls, settings} relationship.
# Users, login_history, and audit_logs are scoped by both organization_id
# and (where relevant) user_id.
#
# No ORM by design (see docs/POSTGRESQL_MIGRATION.md) - raw parameterized
# SQL via psycopg 3, matching the project's existing style.

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL") or (
    "postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={sslmode}".format(
        user=os.environ.get("DATABASE_USER", "outreach_app"),
        password=os.environ.get("DATABASE_PASSWORD", ""),
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=os.environ.get("DATABASE_PORT", "5432"),
        name=os.environ.get("DATABASE_NAME", "outreach"),
        sslmode=os.environ.get("DATABASE_SSLMODE", "prefer"),
    )
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    """One connection per call, closed on exit - safe across the campaign
    runner's background threads (never share a connection between threads).
    Commits on success, rolls back on exception (psycopg's own context
    manager behavior), same transactional guarantee the old sqlite3
    `with get_conn() as conn:` pattern gave call sites."""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ---- Bootstrap ----

def init_db():
    """Schema itself lives in migrations/001_initial_postgres_schema.sql
    (run once, separately). This only seeds the default organization and
    the local-dev demo account, matching the old SQLite auto-seed."""
    with get_conn() as conn:
        org = conn.execute(
            "SELECT id FROM organizations ORDER BY id LIMIT 1"
        ).fetchone()
        if not org:
            org = conn.execute(
                """INSERT INTO organizations (name, slug, status)
                   VALUES ('Outreach', 'outreach', 'active') RETURNING id""",
            ).fetchone()
        organization_id = org["id"]

        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if count == 0:
            conn.execute(
                """INSERT INTO users
                   (organization_id, username, password_hash, client_name, role, status)
                   VALUES (%s, %s, %s, %s, 'SUPER_ADMIN', 'active')""",
                (organization_id, "demo", generate_password_hash("demo123"), "Outreach"),
            )
        else:
            conn.execute(
                "UPDATE users SET role = 'SUPER_ADMIN', status = 'active' WHERE username = 'demo'"
            )

        su_username = os.environ.get("SUPERADMIN_USERNAME")
        su_password = os.environ.get("SUPERADMIN_PASSWORD")
        if su_username and su_password:
            existing = conn.execute(
                "SELECT id FROM users WHERE organization_id = %s AND username = %s",
                (organization_id, su_username),
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO users
                       (organization_id, username, password_hash, client_name, email, role, status)
                       VALUES (%s, %s, %s, %s, %s, 'SUPER_ADMIN', 'active')""",
                    (
                        organization_id, su_username,
                        generate_password_hash(su_password), "Outreach",
                        os.environ.get("SUPERADMIN_EMAIL"),
                    ),
                )
    return organization_id


def get_default_organization_id() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()
        return row["id"] if row else init_db()


def resolve_organization_id(user_id: int) -> int:
    """The tenant boundary for every org-scoped query. Services call this
    from the authenticated user_id (never from a client-supplied value) so
    tenant isolation is enforced here, server-side, regardless of what a
    route handler passes in."""
    with get_conn() as conn:
        row = conn.execute("SELECT organization_id FROM users WHERE id = %s", (user_id,)).fetchone()
        if not row:
            raise ValueError(f"Unknown user_id {user_id}")
        return row["organization_id"]


# ---- Organizations ----

def get_organization(organization_id: int):
    with get_conn() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM organizations WHERE id = %s", (organization_id,)).fetchone()
        )


# ---- Users ----

_SAFE_USER_COLUMNS = (
    "id, organization_id, username, email, first_name, last_name, client_name, role, status, "
    "last_login_at AS last_login, created_at, updated_at"
)


def create_user(username: str, password: str, client_name: str, organization_id: int | None = None,
                 role: str = "AGENT", email: str | None = None,
                 first_name: str | None = None, last_name: str | None = None) -> int:
    organization_id = organization_id or get_default_organization_id()
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO users
               (organization_id, username, password_hash, client_name, email, first_name, last_name, role, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active') RETURNING id""",
            (organization_id, username, generate_password_hash(password), client_name,
             email, first_name, last_name, role),
        ).fetchone()
        return row["id"]


def get_user_by_username(username: str, organization_id: int | None = None):
    with get_conn() as conn:
        if organization_id is not None:
            return conn.execute(
                "SELECT * FROM users WHERE organization_id = %s AND username = %s",
                (organization_id, username),
            ).fetchone()
        # Login doesn't know the org up front - username is unique per-org,
        # not globally, so in the (current) single-org deployment this is
        # unambiguous; a future multi-org login screen would ask for the
        # org/slug first.
        return conn.execute(
            "SELECT * FROM users WHERE username = %s ORDER BY id LIMIT 1", (username,)
        ).fetchone()


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


def list_users(organization_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT {_SAFE_USER_COLUMNS} FROM users WHERE organization_id = %s ORDER BY id",
            (organization_id,),
        ).fetchall()
        return rows_to_list(rows)


def update_user(user_id: int, **fields) -> dict | None:
    allowed = {"email", "first_name", "last_name", "role", "status"}
    data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    with get_conn() as conn:
        if data:
            data["updated_at"] = now_iso()
            cols = ", ".join(f"{k} = %s" for k in data)
            conn.execute(f"UPDATE users SET {cols} WHERE id = %s", [*data.values(), user_id])
        row = conn.execute(
            f"SELECT {_SAFE_USER_COLUMNS} FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        return row_to_dict(row)


def set_user_password(user_id: int, new_password: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
            (generate_password_hash(new_password), now_iso(), user_id),
        )


def touch_last_login(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET last_login_at = %s WHERE id = %s", (now_iso(), user_id))


# ---- Login history & audit logs ----

def add_login_history(username: str, success: bool, user_id: int | None = None,
                       organization_id: int | None = None, failure_reason: str | None = None,
                       ip_address: str | None = None, user_agent: str | None = None) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO login_history
               (organization_id, user_id, username_attempted, success, failure_reason, ip_address, user_agent)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (organization_id, user_id, username, success, failure_reason, ip_address, user_agent),
        ).fetchone()
        return row["id"]


def mark_login_logout(login_history_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE login_history SET logout_at = %s WHERE id = %s", (now_iso(), login_history_id)
        )


def count_recent_login_failures(username: str, window_minutes: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS c FROM login_history
               WHERE username_attempted = %s AND success = FALSE
                 AND login_at >= NOW() - (%s || ' minutes')::interval""",
            (username, window_minutes),
        ).fetchone()
        return row["c"]


def get_login_history(page: int = 1, page_size: int = 25, user_id: int | None = None,
                       organization_id: int | None = None) -> dict:
    clauses, params = [], []
    if organization_id is not None:
        clauses.append("organization_id = %s")
        params.append(organization_id)
    if user_id:
        clauses.append("user_id = %s")
        params.append(user_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = max(page - 1, 0) * page_size
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM login_history {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT id, user_id, username_attempted AS username, success, failure_reason,
                       ip_address, user_agent, login_at, logout_at
                FROM login_history {where} ORDER BY id DESC LIMIT %s OFFSET %s""",
            [*params, page_size, offset],
        ).fetchall()
        items = rows_to_list(rows)
        for item in items:
            item["success"] = 1 if item["success"] else 0
        return {"items": items, "total": total, "page": page, "page_size": page_size}


def add_audit_log(action: str, actor_id: int | None = None, actor_username: str | None = None,
                   organization_id: int | None = None, entity: str | None = None,
                   entity_id: int | None = None, metadata: dict | None = None,
                   ip_address: str | None = None) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO audit_logs
               (organization_id, user_id, username, action, resource_type, resource_id, details, ip_address)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (organization_id, actor_id, actor_username, action, entity, entity_id,
             Jsonb(metadata or {}), ip_address),
        ).fetchone()
        return row["id"]


def get_audit_logs(page: int = 1, page_size: int = 25, action: str = "", entity: str = "",
                    organization_id: int | None = None) -> dict:
    clauses, params = [], []
    if organization_id is not None:
        clauses.append("organization_id = %s")
        params.append(organization_id)
    if action:
        clauses.append("action = %s")
        params.append(action)
    if entity:
        clauses.append("resource_type = %s")
        params.append(entity)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = max(page - 1, 0) * page_size
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM audit_logs {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT id, user_id AS actor_id, username AS actor_username, action,
                       resource_type AS entity, resource_id AS entity_id, details AS metadata,
                       ip_address, created_at
                FROM audit_logs {where} ORDER BY id DESC LIMIT %s OFFSET %s""",
            [*params, page_size, offset],
        ).fetchall()
        return {"items": rows_to_list(rows), "total": total, "page": page, "page_size": page_size}


# ---- Contact lists ----

def create_contact_list(organization_id: int, name: str, filename: str, mapping: dict,
                         row_count: int, valid_count: int, invalid_count: int,
                         created_by: int | None = None) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO contact_lists
               (organization_id, created_by, name, filename, mapping_json, row_count, valid_count, invalid_count)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (organization_id, created_by, name, filename, Jsonb(mapping), row_count, valid_count, invalid_count),
        ).fetchone()
        return row["id"]


def get_contact_lists(organization_id: int):
    with get_conn() as conn:
        return rows_to_list(
            conn.execute(
                "SELECT * FROM contact_lists WHERE organization_id = %s ORDER BY id DESC",
                (organization_id,),
            ).fetchall()
        )


def get_contact_list(organization_id: int, list_id: int):
    with get_conn() as conn:
        return row_to_dict(
            conn.execute(
                "SELECT * FROM contact_lists WHERE organization_id = %s AND id = %s",
                (organization_id, list_id),
            ).fetchone()
        )


def update_contact_list_counts(list_id: int, row_count: int, valid_count: int, invalid_count: int):
    with get_conn() as conn:
        conn.execute(
            """UPDATE contact_lists SET row_count = %s, valid_count = %s, invalid_count = %s,
               updated_at = %s WHERE id = %s""",
            (row_count, valid_count, invalid_count, now_iso(), list_id),
        )


# ---- Contacts ----

def _enrich_patient(item: dict) -> dict:
    if not item:
        return item
    extras = item.get("extras") or {}
    balance = item.get("balance")
    if balance is None and extras.get("balance") is not None:
        try:
            balance = float(extras["balance"])
        except (TypeError, ValueError):
            balance = None
    hospital = item.get("hospital") or item.get("company") or extras.get("hospital") or ""
    item["balance"] = float(balance) if balance is not None else None
    item["hospital"] = hospital
    item["balance_display"] = f"${float(balance):,.2f}" if balance is not None else "—"
    item["validation_errors"] = item.get("validation_errors") or []
    return item


def insert_contacts(organization_id: int, list_id: int, contacts: list) -> list:
    ids = []
    with get_conn() as conn:
        for c in contacts:
            hospital = c.get("hospital") or c.get("company") or ""
            row = conn.execute(
                """INSERT INTO contacts
                   (organization_id, list_id, name, first_name, last_name, phone, email, company,
                    hospital, balance, location, notes, extras, validation_status, validation_errors,
                    calling_status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'not_called')
                   RETURNING id""",
                (
                    organization_id, list_id, c.get("name") or "", c.get("first_name"), c.get("last_name"),
                    c.get("phone"), None, hospital, hospital, c.get("balance"), None, None,
                    Jsonb({"balance": c.get("balance"), "hospital": hospital}),
                    c.get("validation_status", "valid"), Jsonb(c.get("validation_errors") or []),
                ),
            ).fetchone()
            ids.append(row["id"])
    return ids


def get_contacts(
    organization_id: int,
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

    clauses = ["contacts.organization_id = %s"]
    params: list = [organization_id]
    if list_id:
        clauses.append("contacts.list_id = %s")
        params.append(list_id)
    if search:
        clauses.append(
            "(contacts.name ILIKE %s OR contacts.phone ILIKE %s OR contacts.company ILIKE %s OR contacts.hospital ILIKE %s)"
        )
        q = f"%{search}%"
        params.extend([q, q, q, q])
    if status:
        clauses.append("contacts.calling_status = %s")
        params.append(status)
    if validation:
        clauses.append("contacts.validation_status = %s")
        params.append(validation)

    where = " AND ".join(clauses)
    offset = max(page - 1, 0) * page_size

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM contacts WHERE {where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT contacts.*,
                       lc.status AS last_call_status,
                       lc.outcome AS last_call_outcome,
                       lc.duration_sec AS last_call_duration_sec,
                       lc.created_at AS last_call_at,
                       COALESCE(cc.retry_count, 0) + (CASE WHEN cc.id IS NULL THEN 0 ELSE 1 END) AS attempt_count
                FROM contacts
                LEFT JOIN LATERAL (
                    SELECT status, outcome, duration_sec, created_at
                    FROM calls
                    WHERE calls.contact_id = contacts.id
                    ORDER BY calls.id DESC
                    LIMIT 1
                ) lc ON TRUE
                LEFT JOIN campaign_contacts cc
                       ON cc.campaign_id = contacts.last_campaign_id AND cc.contact_id = contacts.id
                WHERE {where}
                ORDER BY contacts.{sort_by} {sort_dir}
                LIMIT %s OFFSET %s""",
            [*params, page_size, offset],
        ).fetchall()
        items = [_enrich_patient(dict(r)) for r in rows]
        return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_contact(organization_id: int, contact_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM contacts WHERE organization_id = %s AND id = %s", (organization_id, contact_id)
        ).fetchone()
        return _enrich_patient(row_to_dict(row)) if row else None


def get_existing_phones(organization_id: int) -> set[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT phone FROM contacts WHERE organization_id = %s AND phone IS NOT NULL AND phone != ''",
            (organization_id,),
        ).fetchall()
    return {row["phone"] for row in rows}


def get_valid_contacts_for_list(organization_id: int, list_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM contacts
               WHERE organization_id = %s AND list_id = %s AND validation_status = 'valid'
               ORDER BY id""",
            (organization_id, list_id),
        ).fetchall()
        return [_enrich_patient(dict(r)) for r in rows]


def get_ready_contacts(organization_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM contacts
               WHERE organization_id = %s AND validation_status = 'valid'
                 AND calling_status IN ('not_called', 'failed', 'no_answer')
               ORDER BY id""",
            (organization_id,),
        ).fetchall()
        return [_enrich_patient(dict(r)) for r in rows]


def update_contact(organization_id: int, contact_id: int, data: dict) -> dict | None:
    existing = get_contact(organization_id, contact_id)
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
               SET name = %s, phone = %s, balance = %s, hospital = %s, company = %s,
                   extras = %s, updated_at = %s
               WHERE organization_id = %s AND id = %s""",
            (name, phone, balance, hospital, hospital, Jsonb({"balance": balance, "hospital": hospital}),
             now_iso(), organization_id, contact_id),
        )
    return get_contact(organization_id, contact_id)


def delete_contact(organization_id: int, contact_id: int) -> bool:
    return delete_contacts(organization_id, [contact_id]) > 0


def delete_contacts(organization_id: int, contact_ids: list[int]) -> int:
    if not contact_ids:
        return 0
    with get_conn() as conn:
        # ON DELETE CASCADE on campaign_contacts/calls handles cleanup, but
        # we still scope the delete itself to owned rows only.
        cur = conn.execute(
            "DELETE FROM contacts WHERE organization_id = %s AND id = ANY(%s)",
            (organization_id, contact_ids),
        )
        return cur.rowcount


def count_contacts(organization_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT
                 COUNT(*) AS total,
                 COUNT(*) FILTER (WHERE validation_status = 'valid') AS valid,
                 COUNT(*) FILTER (WHERE validation_status = 'valid'
                                   AND calling_status IN ('not_called', 'failed', 'no_answer')) AS ready,
                 COUNT(*) FILTER (WHERE calling_status = 'in_progress') AS in_progress,
                 COUNT(*) FILTER (WHERE calling_status = 'completed') AS completed
               FROM contacts WHERE organization_id = %s""",
            (organization_id,),
        ).fetchone()
        return {
            "total": row["total"], "valid": row["valid"], "ready": row["ready"],
            "in_progress": row["in_progress"], "completed": row["completed"],
            "remaining": max(row["total"] - row["completed"], 0),
            "invalid": row["total"] - row["valid"],
        }


def update_contact_calling(contact_id: int, status: str, campaign_id: int | None = None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE contacts SET calling_status = %s, last_called_at = %s,
               last_campaign_id = COALESCE(%s, last_campaign_id), updated_at = %s WHERE id = %s""",
            (status, now_iso(), campaign_id, now_iso(), contact_id),
        )


# ---- Campaigns ----

def create_campaign(organization_id: int, data: dict, created_by: int | None = None) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO campaigns
               (organization_id, created_by, name, status, list_id, voice_id, voice_speed, agent_name,
                opening_message, calling_mode, max_calls, delay_ms, concurrency, total_contacts)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                organization_id, created_by, data["name"], data.get("status", "draft"), data.get("list_id"),
                data.get("voice_id", "af_jessica"), data.get("voice_speed", 1.0),
                data.get("agent_name", "Outreach"), data.get("opening_message"),
                data.get("calling_mode", "sequential"), data.get("max_calls"),
                data.get("delay_ms", 2000), data.get("concurrency", 1), data.get("total_contacts", 0),
            ),
        ).fetchone()
        return row["id"]


def link_campaign_contacts(campaign_id: int, contact_ids: list):
    if not contact_ids:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO campaign_contacts (campaign_id, contact_id, status) VALUES (%s, %s, 'pending') "
                "ON CONFLICT (campaign_id, contact_id) DO NOTHING",
                [(campaign_id, cid) for cid in contact_ids],
            )


def get_campaigns(organization_id: int):
    with get_conn() as conn:
        return rows_to_list(
            conn.execute(
                "SELECT * FROM campaigns WHERE organization_id = %s ORDER BY id DESC", (organization_id,)
            ).fetchall()
        )


def get_campaign(organization_id: int, campaign_id: int):
    with get_conn() as conn:
        return row_to_dict(
            conn.execute(
                "SELECT * FROM campaigns WHERE organization_id = %s AND id = %s",
                (organization_id, campaign_id),
            ).fetchone()
        )


def get_campaign_by_id(campaign_id: int):
    with get_conn() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM campaigns WHERE id = %s", (campaign_id,)).fetchone()
        )


def update_campaign(campaign_id: int, **fields):
    if not fields:
        return
    fields["updated_at"] = now_iso()
    cols = ", ".join(f"{k} = %s" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE campaigns SET {cols} WHERE id = %s", [*fields.values(), campaign_id])


def get_pending_campaign_contacts(campaign_id: int):
    with get_conn() as conn:
        return rows_to_list(
            conn.execute(
                """SELECT cc.*, c.name, c.phone, c.email, c.company, c.location, c.notes,
                          c.first_name, c.last_name, c.hospital, c.balance
                   FROM campaign_contacts cc
                   JOIN contacts c ON c.id = cc.contact_id
                   WHERE cc.campaign_id = %s
                     AND (cc.status = 'pending'
                          OR (cc.status = 'retry_pending' AND cc.next_retry_at <= NOW()))
                   ORDER BY CASE cc.status WHEN 'pending' THEN 0 ELSE 1 END, cc.id""",
                (campaign_id,),
            ).fetchall()
        )


def has_scheduled_retries(campaign_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM campaign_contacts WHERE campaign_id = %s AND status = 'retry_pending'",
            (campaign_id,),
        ).fetchone()
        return bool(row["c"])


def update_campaign_contact(campaign_id: int, contact_id: int, status: str, call_id: int | None = None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE campaign_contacts SET status = %s, call_id = COALESCE(%s, call_id), updated_at = %s
               WHERE campaign_id = %s AND contact_id = %s""",
            (status, call_id, now_iso(), campaign_id, contact_id),
        )


def schedule_retry(campaign_id: int, contact_id: int, retry_count: int, next_retry_at: str):
    with get_conn() as conn:
        conn.execute(
            """UPDATE campaign_contacts
               SET status = 'retry_pending', retry_count = %s, next_retry_at = %s, updated_at = %s
               WHERE campaign_id = %s AND contact_id = %s""",
            (retry_count, next_retry_at, now_iso(), campaign_id, contact_id),
        )


def get_active_campaign(organization_id: int):
    with get_conn() as conn:
        return row_to_dict(
            conn.execute(
                """SELECT * FROM campaigns
                   WHERE organization_id = %s AND status IN ('running', 'paused')
                   ORDER BY updated_at DESC LIMIT 1""",
                (organization_id,),
            ).fetchone()
        )


# ---- Calls ----

def create_call(organization_id: int, campaign_id: int | None, contact_id: int | None, script_text: str,
                 patient: dict | None = None) -> int:
    """`patient`, if given, is snapshotted onto the call row (name/phone/
    hospital/balance) so call history stays meaningful even after the
    patient record is later edited or deleted - the call log must not
    silently go blank just because its source contact is gone."""
    patient = patient or {}
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO calls
               (organization_id, campaign_id, contact_id, patient_name, patient_phone,
                patient_hospital, patient_balance, status, script_text, transcript, events, started_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'in_progress', %s, %s, %s, %s) RETURNING id""",
            (organization_id, campaign_id, contact_id, patient.get("name"), patient.get("phone"),
             patient.get("hospital"), patient.get("balance"), script_text, Jsonb([]), Jsonb([]), now_iso()),
        ).fetchone()
        return row["id"]


def update_call(call_id: int, **fields):
    if not fields:
        return
    for key in ("transcript", "events"):
        if key in fields and not isinstance(fields[key], Jsonb):
            fields[key] = Jsonb(fields[key])
    cols = ", ".join(f"{k} = %s" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE calls SET {cols} WHERE id = %s", [*fields.values(), call_id])


def append_call_event(call_id: int, event: dict):
    with get_conn() as conn:
        row = conn.execute("SELECT events FROM calls WHERE id = %s", (call_id,)).fetchone()
        events = (row["events"] if row else []) or []
        events.append(event)
        conn.execute("UPDATE calls SET events = %s WHERE id = %s", (Jsonb(events), call_id))


def append_transcript(call_id: int, entry: dict):
    with get_conn() as conn:
        row = conn.execute("SELECT transcript FROM calls WHERE id = %s", (call_id,)).fetchone()
        items = (row["transcript"] if row else []) or []
        items.append(entry)
        conn.execute("UPDATE calls SET transcript = %s WHERE id = %s", (Jsonb(items), call_id))


def get_calls(
    organization_id: int,
    *,
    search: str = "",
    status: str = "",
    outcome: str = "",
    campaign_id: int | None = None,
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 25,
):
    clauses = ["calls.organization_id = %s"]
    params: list = [organization_id]
    if outcome:
        clauses.append("calls.outcome = %s")
        params.append(outcome)
    if search:
        clauses.append("(contacts.name ILIKE %s OR contacts.phone ILIKE %s OR campaigns.name ILIKE %s)")
        q = f"%{search}%"
        params.extend([q, q, q])
    if status:
        clauses.append("calls.status = %s")
        params.append(status)
    if campaign_id:
        clauses.append("calls.campaign_id = %s")
        params.append(campaign_id)
    if date_from:
        clauses.append("calls.created_at >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("calls.created_at <= %s")
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
            f"""SELECT calls.*,
                       COALESCE(contacts.name, calls.patient_name) AS contact_name,
                       COALESCE(contacts.phone, calls.patient_phone) AS contact_phone,
                       contacts.company AS contact_company,
                       COALESCE(contacts.hospital, calls.patient_hospital) AS hospital,
                       COALESCE(contacts.balance, calls.patient_balance) AS balance,
                       campaigns.name AS campaign_name,
                       COALESCE(cc.retry_count, 0) + 1 AS attempt_number
                FROM calls
                LEFT JOIN contacts ON contacts.id = calls.contact_id
                LEFT JOIN campaigns ON campaigns.id = calls.campaign_id
                LEFT JOIN campaign_contacts cc
                       ON cc.campaign_id = calls.campaign_id AND cc.contact_id = calls.contact_id
                WHERE {where}
                ORDER BY calls.id DESC
                LIMIT %s OFFSET %s""",
            [*params, page_size, offset],
        ).fetchall()
        items = rows_to_list(rows)
        for item in items:
            if item.get("balance") is not None:
                item["balance_display"] = f"${float(item['balance']):,.2f}"
            else:
                item["balance_display"] = "—"
            item["hospital"] = item.get("hospital") or item.get("contact_company") or "—"
        return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_call(organization_id: int, call_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT calls.*,
                      COALESCE(contacts.name, calls.patient_name) AS contact_name,
                      COALESCE(contacts.phone, calls.patient_phone) AS contact_phone,
                      contacts.email AS contact_email, contacts.company AS contact_company,
                      COALESCE(contacts.hospital, calls.patient_hospital) AS hospital,
                      COALESCE(contacts.balance, calls.patient_balance) AS balance,
                      campaigns.name AS campaign_name,
                      COALESCE(cc.retry_count, 0) + 1 AS attempt_number
               FROM calls
               LEFT JOIN contacts ON contacts.id = calls.contact_id
               LEFT JOIN campaigns ON campaigns.id = calls.campaign_id
               LEFT JOIN campaign_contacts cc
                      ON cc.campaign_id = calls.campaign_id AND cc.contact_id = calls.contact_id
               WHERE calls.organization_id = %s AND calls.id = %s""",
            (organization_id, call_id),
        ).fetchone()
        item = row_to_dict(row)
        if item and item.get("balance") is not None:
            item["balance_display"] = f"${float(item['balance']):,.2f}"
        return item


def get_call_by_provider_sid(call_sid: str):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT calls.*, campaigns.organization_id AS owner_organization_id
               FROM calls LEFT JOIN campaigns ON campaigns.id = calls.campaign_id
               WHERE calls.provider_call_sid = %s""",
            (call_sid,),
        ).fetchone()
        return row_to_dict(row)


def count_calls(organization_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                 COUNT(*) FILTER (WHERE outcome = 'answered') AS answered
               FROM calls WHERE organization_id = %s""",
            (organization_id,),
        ).fetchone()
        return {"completed": row["completed"], "answered": row["answered"]}


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
    "retry_max_attempts": "2",
    "retry_delay_no_answer_ms": str(30 * 60 * 1000),
    "retry_delay_busy_ms": str(15 * 60 * 1000),
    "calling_hours_enabled": "false",
    "calling_hours_start": "09:00",
    "calling_hours_end": "18:00",
    "calling_days": "1,2,3,4,5",
    "timezone": "America/New_York",
    "twilio_mode": os.environ.get("TWILIO_MODE", "test"),
}


def get_settings(organization_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE organization_id = %s", (organization_id,)
        ).fetchall()
    settings = dict(DEFAULT_SETTINGS)
    for r in rows:
        settings[r["key"]] = r["value"]
    return settings


def save_settings(organization_id: int, data: dict):
    with get_conn() as conn:
        for key, value in data.items():
            conn.execute(
                """INSERT INTO settings (organization_id, key, value) VALUES (%s, %s, %s)
                   ON CONFLICT (organization_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()""",
                (organization_id, key, str(value)),
            )


def add_notification(organization_id: int, user_id: int, message: str, level: str = "info"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notifications (organization_id, user_id, message, level) VALUES (%s, %s, %s, %s)",
            (organization_id, user_id, message, level),
        )


def get_notifications(user_id: int, limit: int = 20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id = %s ORDER BY id DESC LIMIT %s",
            (user_id, limit),
        ).fetchall()
        items = rows_to_list(rows)
        for item in items:
            item["read"] = 1 if item.get("is_read") else 0
        return items


def mark_notifications_read(user_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE notifications SET is_read = TRUE, read_at = NOW() WHERE user_id = %s AND is_read = FALSE",
            (user_id,),
        )


# ---- Demo requests (public marketing site leads) ----

def count_recent_demo_requests(ip_address: str, window_minutes: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS c FROM demo_requests
               WHERE ip_address = %s AND created_at >= NOW() - (%s || ' minutes')::interval""",
            (ip_address, window_minutes),
        ).fetchone()
        return row["c"]


def create_demo_request(data: dict, ip_address: str | None = None) -> int:
    address = data.get("address") or {}
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO demo_requests
               (first_name, last_name, email, company_name, job_title, country, phone,
                website, industry, company_size, address_line1, address_line2, city, state,
                postal_code, automation_need, monthly_call_volume, current_process,
                preferred_demo_date, preferred_demo_time, timezone, message, consent, ip_address)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                data.get("first_name"), data.get("last_name"), data.get("email"),
                data.get("company_name"), data.get("job_title"), data.get("country"),
                data.get("phone"), data.get("website"), data.get("industry"),
                data.get("company_size"), address.get("line1"), address.get("line2"),
                address.get("city"), address.get("state"), address.get("postal_code"),
                data.get("automation_need"), data.get("monthly_call_volume"),
                data.get("current_process"), data.get("preferred_demo_date"),
                data.get("preferred_demo_time"), data.get("timezone"), data.get("message"),
                bool(data.get("consent")), ip_address,
            ),
        ).fetchone()
        return row["id"]


def get_demo_requests(page: int = 1, page_size: int = 25, status: str = "") -> dict:
    clauses, params = [], []
    if status:
        clauses.append("status = %s")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = max(page - 1, 0) * page_size

    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM demo_requests {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT * FROM demo_requests {where}
                ORDER BY id DESC LIMIT %s OFFSET %s""",
            [*params, page_size, offset],
        ).fetchall()
        return {"items": rows_to_list(rows), "total": total, "page": page, "page_size": page_size}


def get_demo_request(request_id: int):
    with get_conn() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM demo_requests WHERE id = %s", (request_id,)).fetchone()
        )


def update_demo_request(request_id: int, status: str | None = None, notes: str | None = None):
    fields, params = [], []
    if status is not None:
        fields.append("status = %s")
        params.append(status)
    if notes is not None:
        fields.append("notes = %s")
        params.append(notes)
    if not fields:
        return get_demo_request(request_id)
    fields.append("updated_at = NOW()")
    params.append(request_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE demo_requests SET {', '.join(fields)} WHERE id = %s", params)
    return get_demo_request(request_id)
