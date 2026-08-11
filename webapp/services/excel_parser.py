"""Excel parsing for patient balance notification lists."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

FIELD_ALIASES: dict[str, list[str]] = {
    "name": [
        "name", "full name", "patient name", "patient", "fullname",
        "contact name", "member name",
    ],
    "phone": [
        "phone", "phone number", "mobile", "mobile number", "mobile no",
        "cell", "cellphone", "telephone", "tel", "contact number",
        "phone_number", "phonenumber",
    ],
    "balance": [
        "balance", "pending balance", "outstanding balance", "patient balance",
        "amount", "balance amount", "balance_amount", "due", "amount due",
        "outstanding", "owed",
    ],
    "hospital": [
        "hospital", "hospital name", "facility", "facility name",
        "clinic", "clinic name", "provider", "site",
    ],
}

PHONE_RE = re.compile(r"[\d+]{7,}")
BALANCE_RE = re.compile(r"[^\d.\-]")


def _normalize_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def detect_mapping(columns: list[str]) -> dict[str, str | None]:
    normalized = {_normalize_header(c): c for c in columns}
    mapping: dict[str, str | None] = {field: None for field in FIELD_ALIASES}
    used = set()
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized and normalized[alias] not in used:
                mapping[field] = normalized[alias]
                used.add(normalized[alias])
                break
    return mapping


def mapping_is_confident(mapping: dict[str, str | None]) -> bool:
    return bool(mapping.get("name") and mapping.get("phone") and mapping.get("balance") and mapping.get("hospital"))


def _cell(row: pd.Series, col: str | None) -> str:
    if not col or col not in row.index:
        return ""
    val = row[col]
    if pd.isna(val):
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def normalize_phone(raw: str) -> str:
    if not raw:
        return ""
    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.count("+") > 1:
        cleaned = cleaned.replace("+", "")
        cleaned = "+" + cleaned
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    return cleaned


def parse_balance(raw: str) -> tuple[float | None, str]:
    """Return (numeric_balance, display_string)."""
    if raw is None or str(raw).strip() == "":
        return None, ""
    text = str(raw).strip()
    cleaned = BALANCE_RE.sub("", text.replace(",", ""))
    try:
        amount = float(cleaned)
    except ValueError:
        return None, text
    return amount, f"${amount:,.2f}"


def validate_patient(patient: dict) -> tuple[str, list[str]]:
    errors: list[str] = []
    if not (patient.get("name") or "").strip():
        errors.append("Missing patient name")
    phone = patient.get("phone") or ""
    if not phone:
        errors.append("Missing phone number")
    elif not PHONE_RE.search(re.sub(r"[^\d+]", "", phone)):
        errors.append("Invalid phone number")
    if patient.get("balance") is None:
        errors.append("Invalid balance")
    if not (patient.get("hospital") or "").strip():
        errors.append("Missing hospital")
    return ("valid" if not errors else "invalid"), errors


def mark_duplicates(patients: list[dict], existing_phones: set[str] | None = None) -> list[dict]:
    seen: set[str] = set()
    existing_phones = existing_phones or set()
    for p in patients:
        phone = (p.get("phone") or "").strip()
        if not phone or p.get("validation_status") == "invalid":
            continue
        if phone in seen:
            _flag_duplicate(p, "Duplicate patient")
        elif phone in existing_phones:
            _flag_duplicate(p, "Already in your patient list")
        else:
            seen.add(phone)
    return patients


def _flag_duplicate(patient: dict, message: str) -> None:
    patient["validation_status"] = "duplicate"
    errors = list(patient.get("validation_errors") or [])
    if message not in errors:
        errors.append(message)
    patient["validation_errors"] = errors


def _read_dataframe(path: str) -> pd.DataFrame:
    """Read spreadsheet; prefer strings so phones/balances aren't mangled."""
    lower = path.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    elif lower.endswith(".xls"):
        df = pd.read_excel(path, engine="xlrd", dtype=str)
    else:
        df = pd.read_excel(path, engine="openpyxl", dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    # Normalize NaN-like leftovers after dtype=str reads
    df = df.fillna("")
    return df


def parse_spreadsheet(path: str) -> dict:
    df = _read_dataframe(path)
    columns = list(df.columns)

    if len(df) == 0:
        raise ValueError("This file doesn't contain any records.")
    if not columns or all(str(c).startswith("Unnamed") for c in columns):
        raise ValueError("We couldn't identify the required fields in this file.")

    mapping = detect_mapping(columns)
    return {
        "columns": columns,
        "detected_mapping": mapping,
        "row_count": int(len(df)),
        "requires_mapping": not mapping_is_confident(mapping),
    }


def apply_mapping(path: str, mapping: dict[str, str | None], existing_phones: set[str] | None = None) -> list[dict]:
    df = _read_dataframe(path)
    if len(df) == 0:
        raise ValueError("This file doesn't contain any records.")

    patients: list[dict] = []
    for idx, row in df.iterrows():
        balance_raw = _cell(row, mapping.get("balance"))
        balance_num, balance_display = parse_balance(balance_raw)
        patient = {
            "row_index": int(idx) + 2,
            "name": _cell(row, mapping.get("name")),
            "phone": normalize_phone(_cell(row, mapping.get("phone"))),
            "balance": balance_num,
            "balance_display": balance_display or (balance_raw or "—"),
            "hospital": _cell(row, mapping.get("hospital")),
        }
        status, errors = validate_patient(patient)
        patient["validation_status"] = status
        patient["validation_errors"] = errors
        patients.append(patient)

    return mark_duplicates(patients, existing_phones)
