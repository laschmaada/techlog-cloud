"""TechLog Cloud - Lambda handler behind API Gateway (HTTP API).

Routes (see DESIGN.md):
  POST  /defects
  GET   /defects?status=OPEN
  GET   /defects/{id}
  PATCH /defects/{id}/status
  POST  /defects/{id}/photo-url
  GET   /tails/{tail}/logpage

Auth: API Gateway validates the Cognito JWT. This handler reads the
caller's groups from the verified claims and enforces role rules:
  - raise defect: Mechanic or Certifying
  - change status: Certifying only
Local demo mode: set AUTH_DISABLED=1 to run without Cognito
(caller becomes demo@local in the Certifying group). Never set it
in a deployed stack.
"""

from __future__ import annotations

import json
import os

import logic
import repository

AUTH_DISABLED = os.environ.get("AUTH_DISABLED") == "1"
WRITE_ROLES = {"Mechanic", "Certifying"}
STATUS_ROLES = {"Certifying"}


def _response(status: int, payload) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Authorization,Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
        },
        "body": json.dumps(payload, default=str),
    }


def _caller(event) -> tuple[str, set]:
    if AUTH_DISABLED:
        return "demo@local", {"Mechanic", "Certifying"}
    claims = (event.get("requestContext", {}).get("authorizer", {})
              .get("jwt", {}).get("claims", {}))
    email = claims.get("email") or claims.get("cognito:username") or "unknown"
    groups = claims.get("cognito:groups") or ""
    if isinstance(groups, str):
        groups = {g for g in groups.replace("[", "").replace("]", "").split(" ") if g}
    return email, set(groups)


def _body(event) -> dict:
    raw = event.get("body") or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise logic.ValidationError("Body must be valid JSON")


def handler(event, _context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("requestContext", {}).get("http", {}).get("path", "")
    params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}

    if method == "OPTIONS":
        return _response(200, {})

    email, groups = _caller(event)

    try:
        if method == "POST" and path == "/defects":
            if not groups & WRITE_ROLES:
                return _response(403, {"error": "Your role may not raise defects"})
            clean = logic.validate_new_defect(_body(event))
            defect = logic.build_defect(clean, raised_by=email)
            repository.create_defect(defect)
            if defect["category"] == "AOG":
                repository.notify_aog(defect)
            return _response(201, defect)

        if method == "GET" and path == "/defects":
            status = str(query.get("status", "OPEN")).upper()
            if status not in logic.STATUSES:
                return _response(400, {"error": f"status must be one of {sorted(logic.STATUSES)}"})
            return _response(200, {"defects": repository.list_by_status(status)})

        if method == "GET" and "id" in params and path.startswith("/defects/"):
            result = repository.get_defect_with_history(params["id"])
            if result is None:
                return _response(404, {"error": "Defect not found"})
            return _response(200, result)

        if method == "PATCH" and path.startswith("/defects/"):
            if not groups & STATUS_ROLES:
                return _response(403, {"error": "Only Certifying staff may change defect status"})
            found = repository.get_defect_with_history(params["id"])
            if found is None:
                return _response(404, {"error": "Defect not found"})
            body = _body(event)
            updated, history = logic.apply_transition(
                found["defect"], body.get("action", ""), body, actor=email)
            repository.update_defect(updated, history)
            return _response(200, updated)

        if method == "POST" and path.startswith("/defects/") and path.endswith("/photo-url"):
            if not groups & WRITE_ROLES:
                return _response(403, {"error": "Your role may not attach photos"})
            body = _body(event)
            return _response(200, repository.presign_photo_upload(
                params["id"], str(body.get("contentType", "image/jpeg"))))

        if method == "GET" and path.startswith("/tails/"):
            tail = str(params.get("tail", "")).upper()
            return _response(200, {"tail": tail, "defects": repository.list_by_tail(tail)})

        return _response(404, {"error": "Route not found"})

    except logic.ValidationError as exc:
        return _response(400, {"error": str(exc)})
    except logic.TransitionError as exc:
        return _response(409, {"error": str(exc)})
