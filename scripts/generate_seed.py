#!/usr/bin/env python3
"""Generate synthetic TechLog seed defects and (optionally) load them.

Usage:
    python3 scripts/generate_seed.py            # writes seed.json
    python3 scripts/generate_seed.py --load     # also PUTs each defect
                                                # into the DynamoDB table
                                                # (TABLE_NAME env var, AWS creds required)

All data is synthetic: invented tails, stations and defect texts written
from generic maintenance experience. No real airline data.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import logic  # noqa: E402

SAMPLES = [
    # tail, fleet, ata, station, category, description, then: actions [(action, fields)]
    ("ZS-SXA", "B737-800", "32", "FAOR", "AOG",
     "Nose gear steering judder during taxi-in, felt through tiller below 10 kt, no steering fault on EICAS",
     []),
    ("ZS-SXA", "B737-800", "27", "FACT", "DEFERRAL",
     "Left Krueger flap skin minor dent at station 45, within SRM limits, monitor at next A-check",
     [("defer", {"melRef": "SRM 57-10 / CAT C 10 days"})]),
    ("ZS-SXB", "B737-800", "71", "FAOR", "OBSERVATION",
     "No 1 engine fan blade FOD nick, blend within AMM limits, borescope satisfactory",
     [("rectify", {"rectificationNote": "Blended per AMM 72-00, borescope NFF, fan track within limits"}),
      ("close", {})]),
    ("ZS-SXC", "B737-800", "25", "FALE", "CABIN",
     "Seat 14B tray table latch broken, seat serviceable, placard fitted",
     [("defer", {"melRef": "MEL 25-11 CAT C"})]),
    ("ZS-ZWA", "A320", "29", "FAOR", "AOG",
     "Yellow hydraulic system low pressure on engine start, ELEC pump O/P low, aircraft grounded for pump change",
     []),
    ("ZS-ZWA", "A320", "34", "FADN", "DEFERRAL",
     "Weather radar intermittent sweep drop-out in WX+T mode, no ECAM, deferred for LRU swap at base",
     [("defer", {"melRef": "MEL 34-18 CAT B"})]),
    ("ZS-ZWB", "A320", "21", "FACT", "OBSERVATION",
     "Pack 1 outlet temp fluctuation plus/minus 4 deg in cruise, no fault messages, monitor trend",
     []),
    ("ZS-ZWB", "A320", "52", "FAOR", "DEFERRAL",
     "FWD cargo door seal minor tear at lower aft corner, pressurisation normal, seal on order",
     [("defer", {"melRef": "MEL 52-30 CAT C"})]),
    ("ZS-ZWC", "A320", "24", "FAOR", "OBSERVATION",
     "APU generator load fluctuation noted on turnaround, APU GCU BITE no fault, continue monitoring",
     [("rectify", {"rectificationNote": "APU GCU BITE re-run satisfactory, load stable over 3 sectors, NFF"}),
      ("close", {})]),
    ("ZS-SXB", "B737-800", "38", "FACT", "CABIN",
     "FWD lavatory vacuum blower noisy in operation, flush normal, blower change planned at night stop",
     []),
]


def build_seed() -> list:
    records = []
    for tail, fleet, ata, station, category, desc, actions in SAMPLES:
        clean = logic.validate_new_defect({
            "tail": tail, "fleetType": fleet, "ataChapter": ata,
            "station": station, "description": desc, "category": category,
        })
        defect = logic.build_defect(clean, raised_by="seed@demo.local")
        entries = [logic.created_history(defect)]
        for action, fields in actions:
            defect, entry = logic.apply_transition(
                defect, action, fields, actor="certifying@demo.local")
            entries.append(entry)
        records.append({"defect": defect, "history": entries})
    return records


def main() -> None:
    records = build_seed()
    out = os.path.join(os.path.dirname(__file__), "seed.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)
    print(f"Wrote {len(records)} synthetic defects to {out}")

    if "--load" in sys.argv:
        table_name = os.environ.get("TABLE_NAME")
        if not table_name:
            raise SystemExit("Set TABLE_NAME to your deployed DynamoDB table name first")
        import boto3
        table = boto3.resource("dynamodb").Table(table_name)
        for rec in records:
            table.put_item(Item=logic.to_dynamo_meta(rec["defect"]))
            for entry in rec["history"]:
                table.put_item(Item=logic.to_dynamo_history(rec["defect"]["defectId"], entry))
        print(f"Loaded {len(records)} defects into {table_name}")


if __name__ == "__main__":
    main()
