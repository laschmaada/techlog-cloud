"""DynamoDB / S3 / SNS access for TechLog Cloud.

Thin layer over boto3 (boto3 ships with the Lambda Python runtime,
so there are no dependencies to package). All domain rules live in
logic.py; this module only moves data.
"""

from __future__ import annotations

import os

import boto3
from boto3.dynamodb.conditions import Key

import logic

TABLE_NAME = os.environ.get("TABLE_NAME", "")
DOCS_BUCKET = os.environ.get("DOCS_BUCKET", "")
AOG_TOPIC_ARN = os.environ.get("AOG_TOPIC_ARN", "")

_dynamodb = boto3.resource("dynamodb")
_s3 = boto3.client("s3")
_sns = boto3.client("sns")


def _table():
    return _dynamodb.Table(TABLE_NAME)


def _clean(item: dict) -> dict:
    """Strip single-table key attributes before returning to callers."""
    return {k: v for k, v in item.items()
            if k not in ("PK", "SK", "GSI1PK", "GSI1SK")}


def create_defect(defect: dict) -> None:
    table = _table()
    table.put_item(Item=logic.to_dynamo_meta(defect))
    table.put_item(Item=logic.to_dynamo_history(
        defect["defectId"], logic.created_history(defect)))


def get_defect_with_history(defect_id: str):
    resp = _table().query(KeyConditionExpression=Key("PK").eq(logic.defect_pk(defect_id)))
    items = resp.get("Items", [])
    defect, history, photos = None, [], []
    for item in items:
        if item["SK"] == "META":
            defect = _clean(item)
        elif item["SK"].startswith("HISTORY#"):
            history.append(_clean(item))
        elif item["SK"].startswith("PHOTO#"):
            photos.append(_clean(item))
    if defect is None:
        return None
    history.sort(key=lambda h: h.get("at", ""))
    return {"defect": defect, "history": history, "photos": photos}


def list_by_status(status: str, limit: int = 100) -> list:
    resp = _table().query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(logic.gsi1pk(status)),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [_clean(i) for i in resp.get("Items", [])]


def list_by_tail(tail: str) -> list:
    # MVP trade-off (documented in DESIGN.md): fleet data is small, so the
    # log-page view scans with a filter. Production fix = GSI on tail.
    resp = _table().scan(FilterExpression="tail = :t AND SK = :meta",
                         ExpressionAttributeValues={":t": tail, ":meta": "META"})
    items = [_clean(i) for i in resp.get("Items", [])]
    items.sort(key=lambda d: d.get("createdAt", ""), reverse=True)
    return items


def update_defect(updated: dict, history_entry: dict) -> None:
    table = _table()
    table.put_item(Item=logic.to_dynamo_meta(updated))
    table.put_item(Item=logic.to_dynamo_history(updated["defectId"], history_entry))


def presign_photo_upload(defect_id: str, content_type: str) -> dict:
    photo_id = logic.new_id()
    key = f"defects/{defect_id}/{photo_id}"
    url = _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": DOCS_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=600,
    )
    _table().put_item(Item={
        "PK": logic.defect_pk(defect_id),
        "SK": logic.photo_sk(photo_id),
        "defectId": defect_id,
        "s3Key": key,
        "contentType": content_type,
        "at": logic.now_iso(),
    })
    return {"uploadUrl": url, "s3Key": key}


def notify_aog(defect: dict) -> None:
    if not AOG_TOPIC_ARN:
        return
    _sns.publish(
        TopicArn=AOG_TOPIC_ARN,
        Subject=f"AOG DEFECT {defect['tail']} ATA {defect['ataChapter']} at {defect['station']}",
        Message=(
            f"AOG defect raised on {defect['tail']} ({defect['fleetType']}) "
            f"at {defect['station']}.\nATA {defect['ataChapter']}: {defect['description']}\n"
            f"Raised by {defect['raisedBy']} at {defect['createdAt']}.\n"
            f"Defect ID: {defect['defectId']}"
        ),
    )
