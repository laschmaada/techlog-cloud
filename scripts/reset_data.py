#!/usr/bin/env python3
"""Delete ALL items from the TechLog DynamoDB table (demo data reset).

Used once for the v2 upgrade: clears the v1 seed fleet (ZS-SX*/ZS-ZW*)
before the Highveld Air seed (ZS-LE*) is loaded. This deletes defect
records AND their audit history — it is a demo-data tool, not something
to run against real records.

Usage (TABLE_NAME env var + AWS credentials required):
    python3 scripts/reset_data.py
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    table_name = os.environ.get("TABLE_NAME")
    if not table_name:
        raise SystemExit("Set TABLE_NAME to your deployed DynamoDB table name first")
    import boto3
    table = boto3.resource("dynamodb").Table(table_name)

    deleted = 0
    scan_kwargs = {"ProjectionExpression": "PK, SK"}
    with table.batch_writer() as batch:
        while True:
            resp = table.scan(**scan_kwargs)
            for item in resp.get("Items", []):
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                deleted += 1
            if "LastEvaluatedKey" not in resp:
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    print(f"Deleted {deleted} items from {table_name}")


if __name__ == "__main__":
    main()
