"""Patient import helpers. Preview is temporary; persist only on confirm."""

from __future__ import annotations

import os
from typing import Any

import db
from services import excel_parser

_pending_uploads: dict[int, dict[str, Any]] = {}


def _summarize(patients: list[dict]) -> dict:
    valid = sum(1 for c in patients if c["validation_status"] == "valid")
    duplicate = sum(1 for c in patients if c["validation_status"] == "duplicate")
    invalid = sum(1 for c in patients if c["validation_status"] == "invalid")
    return {
        "row_count": len(patients),
        "valid_count": valid,
        "invalid_count": invalid,
        "duplicate_count": duplicate,
        "attention_count": invalid + duplicate,
    }


def stash_upload(user_id: int, path: str, filename: str) -> dict:
    """Parse file into temporary pending state. Does NOT save patients."""
    organization_id = db.resolve_organization_id(user_id)
    previous = _pending_uploads.pop(user_id, None)
    if previous and previous.get("path") and previous["path"] != path:
        try:
            os.remove(previous["path"])
        except OSError:
            pass

    try:
        parsed = excel_parser.parse_spreadsheet(path)
    except ValueError:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise ValueError("Unable to read this file. Please check the Excel file and try again.") from None

    mapping = parsed["detected_mapping"]
    payload = {
        "path": path,
        "filename": filename,
        "columns": parsed["columns"],
        "detected_mapping": mapping,
        "row_count": parsed["row_count"],
        "requires_mapping": parsed["requires_mapping"],
        "mapping": dict(mapping),
    }
    _pending_uploads[user_id] = payload

    result = {
        "filename": filename,
        "columns": parsed["columns"],
        "detected_mapping": mapping,
        "row_count": parsed["row_count"],
        "requires_mapping": parsed["requires_mapping"],
        "persisted": False,
        "patients": [],
        "contacts": [],
    }

    # When columns are detected, return full preview in the same response
    if not parsed["requires_mapping"]:
        existing_phones = db.get_existing_phones(organization_id)
        patients = excel_parser.apply_mapping(path, mapping, existing_phones)
        summary = _summarize(patients)
        result.update(summary)
        result["patients"] = patients
        result["contacts"] = patients  # backward-compatible key for frontend
        payload["mapping"] = mapping

    return result


def get_pending(user_id: int) -> dict | None:
    return _pending_uploads.get(user_id)


def cancel_pending(user_id: int) -> bool:
    pending = _pending_uploads.pop(user_id, None)
    if not pending:
        return False
    path = pending.get("path")
    if path:
        try:
            os.remove(path)
        except OSError:
            pass
    return True


def preview_with_mapping(user_id: int, mapping: dict) -> dict:
    pending = _pending_uploads.get(user_id)
    if not pending:
        raise ValueError("No file is ready for preview. Please upload an Excel file first.")

    required = ("name", "phone", "balance", "hospital")
    if not all(mapping.get(k) for k in required):
        raise ValueError("We couldn't identify the required fields in this file.")

    organization_id = db.resolve_organization_id(user_id)
    existing_phones = db.get_existing_phones(organization_id)
    patients = excel_parser.apply_mapping(pending["path"], mapping, existing_phones)
    pending["mapping"] = mapping
    summary = _summarize(patients)
    return {
        "filename": pending["filename"],
        "mapping": mapping,
        "patients": patients,
        "contacts": patients,
        "persisted": False,
        **summary,
    }


def confirm_import(user_id: int, mapping: dict, list_name: str | None = None) -> dict:
    pending = _pending_uploads.get(user_id)
    if not pending:
        raise ValueError("No file is ready to import. Please upload an Excel file first.")

    required = ("name", "phone", "balance", "hospital")
    if not all(mapping.get(k) for k in required):
        raise ValueError("We couldn't identify the required fields in this file.")

    organization_id = db.resolve_organization_id(user_id)
    existing_phones = db.get_existing_phones(organization_id)
    patients = excel_parser.apply_mapping(pending["path"], mapping, existing_phones)
    summary = _summarize(patients)
    to_import = [c for c in patients if c["validation_status"] == "valid"]
    if not to_import:
        raise ValueError("There are no ready patients to import.")

    name = list_name or os.path.splitext(pending["filename"])[0]
    list_id = db.create_contact_list(
        organization_id=organization_id,
        name=name,
        filename=pending["filename"],
        mapping=mapping,
        row_count=summary["row_count"],
        valid_count=summary["valid_count"],
        invalid_count=summary["attention_count"],
        created_by=user_id,
    )
    db.insert_contacts(organization_id, list_id, to_import)
    db.add_notification(organization_id, user_id, f"{len(to_import)} patients are ready", "success")

    path = pending.get("path")
    _pending_uploads.pop(user_id, None)
    if path:
        try:
            os.remove(path)
        except OSError:
            pass

    return {
        "list_id": list_id,
        "name": name,
        "filename": pending["filename"],
        "imported_count": len(to_import),
        "persisted": True,
        **summary,
    }


def add_contact(user_id: int, data: dict) -> dict:
    """Add a single patient manually (no Excel file involved)."""
    organization_id = db.resolve_organization_id(user_id)
    balance_num, balance_display = excel_parser.parse_balance(data.get("balance"))
    patient = {
        "name": (data.get("name") or "").strip(),
        "phone": excel_parser.normalize_phone((data.get("phone") or "").strip()),
        "balance": balance_num,
        "balance_display": balance_display,
        "hospital": (data.get("hospital") or "").strip(),
    }
    status, errors = excel_parser.validate_patient(patient)
    if status != "valid":
        raise ValueError(errors[0] if errors else "Please check the patient details.")

    if patient["phone"] in db.get_existing_phones(organization_id):
        raise ValueError("A patient with this phone number already exists.")

    patient["validation_status"] = "valid"
    patient["validation_errors"] = []
    ids = db.insert_contacts(organization_id, None, [patient])
    return db.get_contact(organization_id, ids[0])


def list_contacts(user_id: int, **filters):
    return db.get_contacts(db.resolve_organization_id(user_id), **filters)


def get_contact(user_id: int, contact_id: int):
    return db.get_contact(db.resolve_organization_id(user_id), contact_id)


def update_contact(user_id: int, contact_id: int, data: dict):
    return db.update_contact(db.resolve_organization_id(user_id), contact_id, data)


def delete_contact(user_id: int, contact_id: int) -> bool:
    return db.delete_contact(db.resolve_organization_id(user_id), contact_id)


def delete_contacts(user_id: int, contact_ids: list[int]) -> int:
    return db.delete_contacts(db.resolve_organization_id(user_id), contact_ids)


def list_lists(user_id: int):
    return db.get_contact_lists(db.resolve_organization_id(user_id))
