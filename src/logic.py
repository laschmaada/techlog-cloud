"""TechLog Cloud - pure domain logic.

No AWS imports here on purpose: every rule that matters (validation,
workflow transitions, audit entries) is unit-testable without boto3,
DynamoDB, or a network. app.py wires this to Lambda/API Gateway,
repository.py wires it to DynamoDB.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

CATEGORIES = {"AOG", "DEFERRAL", "CABIN", "OBSERVATION"}
STATUSES = {"OPEN", "DEFERRED", "RECTIFIED", "CLOSED"}
FLEET_TYPES = {"B737-800", "A320"}

# Workflow state machine: (from_status, action) -> to_status
# action -> required extra field
TRANSITIONS = {
    ("OPEN", "defer"): "DEFERRED",
    ("OPEN", "rectify"): "RECTIFIED",
    ("DEFERRED", "rectify"): "RECTIFIED",
    ("RECTIFIED", "close"): "CLOSED",
    ("CLOSED", "reopen"): "OPEN",
}
ACTION_REQUIRED_FIELD = {
    "defer": "melRef",
    "rectify": "rectificationNote",
    "reopen": "reason",
    "close": None,
}
ACTION_HISTORY_EVENT = {
    "defer": "DEFERRED",
    "rectify": "RECTIFIED",
    "close": "CLOSED",
    "reopen": "REOPENED",
}

_TAIL_RE = re.compile(r"^ZS-[A-Z]{3}$")
_ATA_RE = re.compile(r"^\d{2}$")
_STATION_RE = re.compile(r"^[A-Z]{4}$")


class ValidationError(ValueError):
    """Caller sent something invalid -> HTTP 400."""


class TransitionError(ValueError):
    """Workflow transition not allowed -> HTTP 409."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_id() -> str:
    return str(uuid.uuid4())


def validate_new_defect(body: dict) -> dict:
    """Validate a raise-defect request body. Returns a cleaned dict."""
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")

    tail = str(body.get("tail", "")).strip().upper()
    if not _TAIL_RE.match(tail):
        raise ValidationError("tail must look like ZS-XXX (synthetic fleet)")

    fleet = str(body.get("fleetType", "")).strip()
    if fleet not in FLEET_TYPES:
        raise ValidationError(f"fleetType must be one of {sorted(FLEET_TYPES)}")

    ata = str(body.get("ataChapter", "")).strip()
    if not _ATA_RE.match(ata) or not (11 <= int(ata) <= 99):
        raise ValidationError("ataChapter must be a 2-digit ATA chapter (e.g. 27, 32, 71)")

    station = str(body.get("station", "")).strip().upper()
    if not _STATION_RE.match(station):
        raise ValidationError("station must be a 4-letter ICAO code (e.g. FAOR)")

    description = str(body.get("description", "")).strip()
    if len(description) < 10:
        raise ValidationError("description must be at least 10 characters - write it like a log entry")

    category = str(body.get("category", "")).strip().upper()
    if category not in CATEGORIES:
        raise ValidationError(f"category must be one of {sorted(CATEGORIES)}")

    return {
        "tail": tail,
        "fleetType": fleet,
        "ataChapter": ata,
        "station": station,
        "description": description,
        "category": category,
    }


def build_defect(clean: dict, raised_by: str) -> dict:
    ts = now_iso()
    defect_id = new_id()
    return {
        "defectId": defect_id,
        "tail": clean["tail"],
        "fleetType": clean["fleetType"],
        "ataChapter": clean["ataChapter"],
        "station": clean["station"],
        "description": clean["description"],
        "category": clean["category"],
        "status": "OPEN",
        "melRef": None,
        "raisedBy": raised_by,
        "createdAt": ts,
        "updatedAt": ts,
    }


def apply_transition(defect: dict, action: str, body: dict, actor: str) -> tuple[dict, dict]:
    """Validate and apply a workflow action.

    Returns (updated_defect, history_entry). Raises TransitionError for
    illegal moves and ValidationError for missing required fields.
    The original dict is not mutated.
    """
    action = str(action or "").strip().lower()
    if action not in ACTION_REQUIRED_FIELD:
        raise ValidationError(f"action must be one of {sorted(ACTION_REQUIRED_FIELD)}")

    current = defect["status"]
    key = (current, action)
    if key not in TRANSITIONS:
        raise TransitionError(f"Cannot {action} a defect in status {current}")

    required = ACTION_REQUIRED_FIELD[action]
    value = None
    if required:
        value = str((body or {}).get(required, "")).strip()
        if not value:
            raise ValidationError(f"{required} is required to {action} a defect")

    updated = dict(defect)
    updated["status"] = TRANSITIONS[key]
    updated["updatedAt"] = now_iso()
    if action == "defer":
        updated["melRef"] = value
    if action == "rectify":
        updated["rectificationNote"] = value
        updated["rectifiedBy"] = actor
    if action == "close":
        updated["closedBy"] = actor
    if action == "reopen":
        updated["melRef"] = None

    history = {
        "event": ACTION_HISTORY_EVENT[action],
        "fromStatus": current,
        "toStatus": updated["status"],
        "actor": actor,
        "at": updated["updatedAt"],
        "detail": value,
    }
    return updated, history


def created_history(defect: dict) -> dict:
    return {
        "event": "CREATED",
        "fromStatus": None,
        "toStatus": "OPEN",
        "actor": defect["raisedBy"],
        "at": defect["createdAt"],
        "detail": defect["description"],
    }


# --- DynamoDB key helpers (single-table design, see DESIGN.md) ---

def defect_pk(defect_id: str) -> str:
    return f"DEFECT#{defect_id}"


def meta_sk() -> str:
    return "META"


def history_sk(at: str, entry_id: str) -> str:
    return f"HISTORY#{at}#{entry_id}"


def photo_sk(photo_id: str) -> str:
    return f"PHOTO#{photo_id}"


def gsi1pk(status: str) -> str:
    return f"STATUS#{status}"


def gsi1sk(defect: dict) -> str:
    return f"{defect['createdAt']}#{defect['defectId']}"


def to_dynamo_meta(defect: dict) -> dict:
    item = dict(defect)
    item["PK"] = defect_pk(defect["defectId"])
    item["SK"] = meta_sk()
    item["GSI1PK"] = gsi1pk(defect["status"])
    item["GSI1SK"] = gsi1sk(defect)
    # DynamoDB rejects None in plain dict writes via boto3 resource API
    return {k: v for k, v in item.items() if v is not None}


def to_dynamo_history(defect_id: str, entry: dict) -> dict:
    item = dict(entry)
    item["PK"] = defect_pk(defect_id)
    item["SK"] = history_sk(entry["at"], new_id())
    item["defectId"] = defect_id
    return {k: v for k, v in item.items() if v is not None}
