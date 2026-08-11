"""Backend smoke tests. Run with:  python -m unittest discover -s tests

Runs against a dedicated `outreach_test` PostgreSQL database (see
migrations/001_initial_postgres_schema.sql) - never touches the real
`outreach` database. Covers the load-bearing fixes/features from this
project: auth + RBAC, login rate limiting, duplicate detection (in-file
and against-DB), cascading contact delete, and multi-tenant isolation.
"""

from __future__ import annotations

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Point at the dedicated test database before db.py (which reads these at
# import time) is imported.
os.environ["DATABASE_NAME"] = "outreach_test"
os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DATABASE_USER", "outreach_app")
os.environ.setdefault("DATABASE_PASSWORD", "root")
os.environ.setdefault("DATABASE_SSLMODE", "prefer")

import db  # noqa: E402

with db.get_conn() as _conn:
    _conn.execute(
        "TRUNCATE audit_logs, login_history, notifications, calls, campaign_contacts, "
        "campaigns, contacts, contact_lists, users, organizations RESTART IDENTITY CASCADE"
    )
db.init_db()

import app as flask_app_module  # noqa: E402 - imports after DATABASE_* env vars are set
from services import excel_parser  # noqa: E402


class AuthAndRbacTests(unittest.TestCase):
    def setUp(self):
        self.app = flask_app_module.app
        self.app.testing = True
        self.client = self.app.test_client()

    def _login(self, username, password):
        return self.client.post("/api/auth/login", json={"username": username, "password": password})

    def test_login_success_returns_role(self):
        res = self._login("demo", "demo123")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["user"]["role"], "SUPER_ADMIN")

    def test_login_invalid_credentials_rejected(self):
        res = self._login("demo", "wrong-password")
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.get_json()["ok"])

    def test_login_does_not_reveal_username_existence(self):
        bad_user = self._login("no-such-user", "whatever").get_json()
        bad_pass = self._login("demo", "wrong-password").get_json()
        self.assertEqual(bad_user["error"], bad_pass["error"])

    def test_login_rate_limited_after_repeated_failures(self):
        for _ in range(5):
            self._login("ratelimit-target", "wrong")
        res = self._login("ratelimit-target", "wrong")
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.get_json()["error_code"], "RATE_LIMITED")

    def test_rbac_blocks_viewer_role_from_admin_endpoint(self):
        self._login("demo", "demo123")
        self.client.post(
            "/api/admin/users",
            json={"username": "viewer_smoketest", "password": "testpass123", "role": "VIEWER"},
        )
        self.client.post("/api/auth/logout")

        self._login("viewer_smoketest", "testpass123")
        res = self.client.get("/api/admin/users")
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_request_rejected(self):
        client = self.app.test_client()
        res = client.get("/api/contacts")
        self.assertEqual(res.status_code, 401)


class DuplicateDetectionTests(unittest.TestCase):
    def test_marks_duplicate_within_same_file(self):
        patients = [
            {"phone": "+15551234567", "validation_status": "valid", "validation_errors": []},
            {"phone": "+15551234567", "validation_status": "valid", "validation_errors": []},
        ]
        result = excel_parser.mark_duplicates(patients)
        self.assertEqual(result[0]["validation_status"], "valid")
        self.assertEqual(result[1]["validation_status"], "duplicate")
        self.assertIn("Duplicate patient", result[1]["validation_errors"])

    def test_marks_duplicate_against_existing_database_phones(self):
        patients = [{"phone": "+15559998888", "validation_status": "valid", "validation_errors": []}]
        result = excel_parser.mark_duplicates(patients, existing_phones={"+15559998888"})
        self.assertEqual(result[0]["validation_status"], "duplicate")
        self.assertIn("Already in your patient list", result[0]["validation_errors"])

    def test_does_not_flag_unique_new_phone(self):
        patients = [{"phone": "+15550001111", "validation_status": "valid", "validation_errors": []}]
        result = excel_parser.mark_duplicates(patients, existing_phones={"+15559998888"})
        self.assertEqual(result[0]["validation_status"], "valid")


class DeleteCascadeTests(unittest.TestCase):
    def test_delete_contact_with_existing_call_history_does_not_raise(self):
        user = db.get_user_by_username("demo")
        organization_id = user["organization_id"]
        list_id = db.create_contact_list(organization_id, "Test list", "test.xlsx", {}, 1, 1, 0)
        contact_ids = db.insert_contacts(
            organization_id, list_id,
            [{"name": "Test Patient", "phone": "+15557654321", "balance": 100, "hospital": "Test Hospital",
              "validation_status": "valid", "validation_errors": []}],
        )
        contact_id = contact_ids[0]
        campaign_id = db.create_campaign(organization_id, {"name": "Test Campaign", "total_contacts": 1})
        db.link_campaign_contacts(campaign_id, [contact_id])
        call_id = db.create_call(organization_id, campaign_id, contact_id, "test script")
        db.update_call(call_id, status="completed", outcome="answered")

        deleted = db.delete_contacts(organization_id, [contact_id])
        self.assertEqual(deleted, 1)
        self.assertIsNone(db.get_contact(organization_id, contact_id))


class RetryEngineTests(unittest.TestCase):
    def test_calling_hours_disabled_always_allows_calling(self):
        from services.call_runner import _within_calling_hours
        self.assertTrue(_within_calling_hours({"calling_hours_enabled": "false"}))

    def test_invalid_phone_detection(self):
        from services.call_runner import _is_valid_phone
        self.assertTrue(_is_valid_phone("+15551234567"))
        self.assertFalse(_is_valid_phone("not-a-phone"))
        self.assertFalse(_is_valid_phone(""))
        self.assertFalse(_is_valid_phone(None))


class MultiTenantIsolationTests(unittest.TestCase):
    """Organization A must never be able to read Organization B's data,
    even when both are queried through the exact same db.py functions."""

    def test_contacts_are_isolated_by_organization(self):
        with db.get_conn() as conn:
            org_a = conn.execute(
                "INSERT INTO organizations (name, slug) VALUES ('Org A', 'org-a-test') RETURNING id"
            ).fetchone()["id"]
            org_b = conn.execute(
                "INSERT INTO organizations (name, slug) VALUES ('Org B', 'org-b-test') RETURNING id"
            ).fetchone()["id"]

        list_a = db.create_contact_list(org_a, "A's list", "a.xlsx", {}, 1, 1, 0)
        db.insert_contacts(org_a, list_a, [
            {"name": "Org A Patient", "phone": "+15551110001", "balance": 1,
             "validation_status": "valid", "validation_errors": []},
        ])

        # Org B has no contacts at all - it must see zero, not Org A's data.
        result_b = db.get_contacts(org_b)
        self.assertEqual(result_b["total"], 0)
        self.assertEqual(result_b["items"], [])

        # Org A sees its own contact.
        result_a = db.get_contacts(org_a)
        self.assertEqual(result_a["total"], 1)
        self.assertEqual(result_a["items"][0]["name"], "Org A Patient")


class TwilioClientTests(unittest.TestCase):
    def test_simulated_call_maps_to_simulated_outcome_not_answered_or_failed(self):
        from services import twilio_client
        call_status, outcome = twilio_client.map_status("queued", simulated=True)
        self.assertEqual(call_status, "completed")
        self.assertEqual(outcome, "simulated")

    def test_real_terminal_statuses_map_correctly(self):
        from services import twilio_client
        self.assertEqual(twilio_client.map_status("completed"), ("completed", "answered"))
        self.assertEqual(twilio_client.map_status("busy"), ("failed", "busy"))
        self.assertEqual(twilio_client.map_status("no-answer"), ("no_answer", "no_answer"))
        self.assertEqual(twilio_client.map_status("failed"), ("failed", "failed"))

    def test_not_configured_without_credentials(self):
        from services import twilio_client
        old = {k: os.environ.pop(k, None) for k in
               ("TWILIO_TEST_ACCOUNT_SID", "TWILIO_TEST_AUTH_TOKEN", "TWILIO_FROM_NUMBER")}
        try:
            self.assertFalse(twilio_client.is_configured("test"))
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v

    def test_webhook_rejects_unrecognized_account_sid(self):
        client = flask_app_module.app.test_client()
        res = client.post(
            "/api/webhooks/twilio/status",
            data={"CallSid": "CAxxxx", "CallStatus": "completed", "AccountSid": "ACunrecognized"},
        )
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
