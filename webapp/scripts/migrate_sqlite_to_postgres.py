"""One-time data migration: copies real data from the old app.db (SQLite)
into the new PostgreSQL `outreach` database. Safe to re-run (idempotent -
skips rows that already exist by id). Does NOT touch/delete app.db.

Usage (from webapp/):
    python scripts/migrate_sqlite_to_postgres.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import db  # noqa: E402 - the new PostgreSQL db module
from psycopg.types.json import Jsonb  # noqa: E402

SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.db")


def _sqlite_conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(pg_conn, table: str, row_id) -> bool:
    return pg_conn.execute(f"SELECT 1 FROM {table} WHERE id = %s", (row_id,)).fetchone() is not None


def migrate():
    sconn = _sqlite_conn()
    organization_id = db.get_default_organization_id()
    print(f"Target organization_id: {organization_id}")

    with db.get_conn() as pconn:
        # ---- users ----
        users = sconn.execute("SELECT * FROM users ORDER BY id").fetchall()
        print(f"\nusers: {len(users)} rows in SQLite")
        for u in users:
            existing = pconn.execute(
                "SELECT id FROM users WHERE organization_id = %s AND username = %s",
                (organization_id, u["username"]),
            ).fetchone()
            if existing:
                pconn.execute(
                    """UPDATE users SET email = %s, first_name = %s, last_name = %s, client_name = %s,
                       password_hash = %s, role = %s, status = %s, last_login_at = %s,
                       created_at = %s, updated_at = %s
                       WHERE id = %s""",
                    (u["email"], u["first_name"], u["last_name"], u["client_name"], u["password_hash"],
                     u["role"], u["status"], u["last_login"], u["created_at"], u["updated_at"] or u["created_at"],
                     existing["id"]),
                )
                print(f"  updated existing user '{u['username']}' -> id {existing['id']}")
            else:
                pconn.execute(
                    """INSERT INTO users
                       (id, organization_id, username, email, first_name, last_name, client_name,
                        password_hash, role, status, last_login_at, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (u["id"], organization_id, u["username"], u["email"], u["first_name"], u["last_name"],
                     u["client_name"], u["password_hash"], u["role"], u["status"], u["last_login"],
                     u["created_at"], u["updated_at"] or u["created_at"]),
                )
                print(f"  inserted user '{u['username']}' (id {u['id']})")

        # ---- contact_lists ----
        lists = sconn.execute("SELECT * FROM contact_lists ORDER BY id").fetchall()
        print(f"\ncontact_lists: {len(lists)} rows in SQLite")
        for cl in lists:
            if _table_exists(pconn, "contact_lists", cl["id"]):
                continue
            pconn.execute(
                """INSERT INTO contact_lists
                   (id, organization_id, name, filename, mapping_json, row_count, valid_count, invalid_count, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (cl["id"], organization_id, cl["name"], cl["filename"],
                 Jsonb(json.loads(cl["mapping_json"] or "{}")), cl["row_count"], cl["valid_count"],
                 cl["invalid_count"], cl["created_at"]),
            )
        print(f"  migrated {len(lists)} contact_lists")

        # ---- contacts ----
        contacts = sconn.execute("SELECT * FROM contacts ORDER BY id").fetchall()
        print(f"\ncontacts: {len(contacts)} rows in SQLite")
        migrated = 0
        for c in contacts:
            if _table_exists(pconn, "contacts", c["id"]):
                continue
            pconn.execute(
                """INSERT INTO contacts
                   (id, organization_id, list_id, name, first_name, last_name, phone, email, company,
                    hospital, balance, location, notes, extras, validation_status, validation_errors,
                    calling_status, last_called_at, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    c["id"], organization_id, c["list_id"], c["name"], c["first_name"], c["last_name"],
                    c["phone"], c["email"], c["company"], c["hospital"], c["balance"], c["location"], c["notes"],
                    Jsonb(json.loads(c["extras_json"] or "{}")), c["validation_status"],
                    Jsonb(json.loads(c["validation_errors"] or "[]")), c["calling_status"],
                    c["last_called_at"], c["created_at"], c["updated_at"],
                ),
            )
            migrated += 1
        print(f"  migrated {migrated} contacts")

        # ---- campaigns ----
        campaigns = sconn.execute("SELECT * FROM campaigns ORDER BY id").fetchall()
        print(f"\ncampaigns: {len(campaigns)} rows in SQLite")
        for cam in campaigns:
            if _table_exists(pconn, "campaigns", cam["id"]):
                continue
            pconn.execute(
                """INSERT INTO campaigns
                   (id, organization_id, created_by, name, status, list_id, voice_id, voice_speed, agent_name,
                    opening_message, calling_mode, max_calls, delay_ms, concurrency, total_contacts,
                    completed_calls, successful_calls, no_answer_calls, failed_calls, simulated_calls,
                    in_progress_calls, current_contact_id, current_call_id, agent_state, error_message,
                    started_at, completed_at, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    cam["id"], organization_id, cam["user_id"], cam["name"], cam["status"], cam["list_id"],
                    cam["voice_id"], cam["voice_speed"], cam["agent_name"], cam["opening_message"],
                    cam["calling_mode"], cam["max_calls"], cam["delay_ms"], cam["concurrency"],
                    cam["total_contacts"], cam["completed_calls"], cam["successful_calls"],
                    cam["no_answer_calls"], cam["failed_calls"], cam["simulated_calls"] or 0,
                    cam["in_progress_calls"], cam["current_contact_id"], cam["current_call_id"],
                    cam["agent_state"], cam["error_message"], cam["started_at"], cam["completed_at"],
                    cam["created_at"], cam["updated_at"],
                ),
            )
        print(f"  migrated {len(campaigns)} campaigns")

        # ---- campaign_contacts ----
        ccs = sconn.execute("SELECT * FROM campaign_contacts ORDER BY id").fetchall()
        print(f"\ncampaign_contacts: {len(ccs)} rows in SQLite")
        for cc in ccs:
            if _table_exists(pconn, "campaign_contacts", cc["id"]):
                continue
            pconn.execute(
                """INSERT INTO campaign_contacts
                   (id, campaign_id, contact_id, status, call_id, retry_count, next_retry_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (cc["id"], cc["campaign_id"], cc["contact_id"], cc["status"], cc["call_id"],
                 cc["retry_count"], cc["next_retry_at"]),
            )
        print(f"  migrated {len(ccs)} campaign_contacts")

        # ---- calls ----
        calls = sconn.execute("SELECT * FROM calls ORDER BY id").fetchall()
        print(f"\ncalls: {len(calls)} rows in SQLite")
        for call in calls:
            if _table_exists(pconn, "calls", call["id"]):
                continue
            pconn.execute(
                """INSERT INTO calls
                   (id, organization_id, campaign_id, contact_id, provider_call_sid, status, outcome,
                    duration_sec, script_text, transcript, events, detail, audio_filename,
                    started_at, ended_at, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    call["id"], organization_id, call["campaign_id"], call["contact_id"],
                    call["provider_call_sid"], call["status"], call["outcome"], call["duration_sec"] or 0,
                    call["script_text"], Jsonb(json.loads(call["transcript_json"] or "[]")),
                    Jsonb(json.loads(call["events_json"] or "[]")), call["detail"], call["audio_filename"],
                    call["started_at"], call["ended_at"], call["created_at"],
                ),
            )
        print(f"  migrated {len(calls)} calls")

        # ---- settings (was per-user, becomes org-scoped: prefer the first/demo user's rows) ----
        settings_rows = sconn.execute("SELECT * FROM settings ORDER BY user_id, key").fetchall()
        print(f"\nsettings: {len(settings_rows)} rows in SQLite")
        seen_keys = set()
        for s in settings_rows:
            if s["key"] in seen_keys:
                continue
            seen_keys.add(s["key"])
            pconn.execute(
                """INSERT INTO settings (organization_id, key, value) VALUES (%s, %s, %s)
                   ON CONFLICT (organization_id, key) DO UPDATE SET value = EXCLUDED.value""",
                (organization_id, s["key"], s["value"]),
            )
        print(f"  migrated {len(seen_keys)} distinct settings keys")

        # ---- notifications ----
        notifications = sconn.execute("SELECT * FROM notifications ORDER BY id").fetchall()
        print(f"\nnotifications: {len(notifications)} rows in SQLite")
        for n in notifications:
            if _table_exists(pconn, "notifications", n["id"]):
                continue
            pconn.execute(
                """INSERT INTO notifications (id, organization_id, user_id, message, level, is_read, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (n["id"], organization_id, n["user_id"], n["message"], n["level"], bool(n["read"]), n["created_at"]),
            )
        print(f"  migrated {len(notifications)} notifications")

        # ---- login_history ----
        logins = sconn.execute("SELECT * FROM login_history ORDER BY id").fetchall()
        print(f"\nlogin_history: {len(logins)} rows in SQLite")
        for lh in logins:
            if _table_exists(pconn, "login_history", lh["id"]):
                continue
            pconn.execute(
                """INSERT INTO login_history
                   (id, organization_id, user_id, username_attempted, success, failure_reason,
                    ip_address, user_agent, login_at, logout_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (lh["id"], organization_id, lh["user_id"], lh["username"], bool(lh["success"]),
                 lh["failure_reason"], lh["ip_address"], lh["user_agent"], lh["login_at"], lh["logout_at"]),
            )
        print(f"  migrated {len(logins)} login_history rows")

        # ---- audit_logs ----
        audits = sconn.execute("SELECT * FROM audit_logs ORDER BY id").fetchall()
        print(f"\naudit_logs: {len(audits)} rows in SQLite")
        for a in audits:
            if _table_exists(pconn, "audit_logs", a["id"]):
                continue
            pconn.execute(
                """INSERT INTO audit_logs
                   (id, organization_id, user_id, username, action, resource_type, resource_id, details,
                    ip_address, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (a["id"], organization_id, a["actor_id"], a["actor_username"], a["action"], a["entity"],
                 a["entity_id"], Jsonb(json.loads(a["metadata_json"] or "{}")), a["ip_address"], a["created_at"]),
            )
        print(f"  migrated {len(audits)} audit_logs rows")

        # ---- bump sequences past the migrated explicit ids ----
        for table in ("users", "contact_lists", "contacts", "campaigns", "campaign_contacts",
                      "calls", "notifications", "login_history", "audit_logs"):
            pconn.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )

    sconn.close()
    print("\nMigration complete.")


def validate():
    sconn = _sqlite_conn()
    print("\n=== Row count validation (SQLite -> PostgreSQL) ===")
    tables = ["users", "contact_lists", "contacts", "campaigns", "campaign_contacts",
              "calls", "settings", "notifications", "login_history", "audit_logs"]
    with db.get_conn() as pconn:
        organization_id = db.get_default_organization_id()
        ok = True
        for t in tables:
            s_count = sconn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            if t == "settings":
                p_count = len(set(r["key"] for r in pconn.execute(
                    "SELECT key FROM settings WHERE organization_id = %s", (organization_id,)
                ).fetchall()))
                s_count = len(set(r["key"] for r in sconn.execute("SELECT DISTINCT key FROM settings").fetchall()))
            elif t == "users":
                p_count = pconn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            else:
                p_count = pconn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
            match = "OK" if s_count == p_count else "MISMATCH"
            if s_count != p_count:
                ok = False
            print(f"  {t:20s} sqlite={s_count:4d}  postgres={p_count:4d}  [{match}]")
    sconn.close()
    return ok


if __name__ == "__main__":
    migrate()
    validate()
