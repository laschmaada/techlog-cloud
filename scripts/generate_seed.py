#!/usr/bin/env python3
"""Generate synthetic TechLog seed defects and (optionally) load them.

Usage:
    python3 scripts/generate_seed.py            # writes seed.json
    python3 scripts/generate_seed.py --load     # also PUTs each defect
                                                # into the DynamoDB table
                                                # (TABLE_NAME env var, AWS creds required)

v2 seed: Highveld Air — a fictional South African domestic airline.
Fleet: 20 x Airbus A320, ZS-LEA to ZS-LET, base FAOR (OR Tambo).
Defect texts are drawn from the A320 snag library built out of the
Airbus Technical Training Manual (derived and paraphrased; see the
aviation-cloud-portfolio snag-library). All data is synthetic.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import logic  # noqa: E402

SAMPLES = [
    # tail, fleet, ata, station, category, description, actions [(action, fields)]
    ("ZS-LEA", "A320", "29", "FAOR", "AOG",
     "HYD Y SYS LO PR on engine start, yellow ELEC pump output low, aircraft grounded for pump change",
     []),
    ("ZS-LEA", "A320", "26", "FAOR", "DEFERRAL",
     "ENG 2 FIRE DET LOOP B FAULT on ECAM during pre-flight, loop A normal",
     [("defer", {"melRef": "MEL 26-10 CAT B"})]),
    ("ZS-LEB", "A320", "32", "FACT", "AOG",
     "L/G NOT DOWNLOCKED red indication RH main gear on approach, recycled to three greens, inspection required before further flight",
     []),
    ("ZS-LEB", "A320", "21", "FALE", "CABIN",
     "Aft cabin zone uncontrollably hot, cockpit and fwd cabin normal, trim air valve suspect",
     [("defer", {"melRef": "MEL 21-63 CAT C"})]),
    ("ZS-LEC", "A320", "24", "FAOR", "DEFERRAL",
     "IDG 1 oil outlet temperature advisory on every flight this week, peak values creeping up sector by sector",
     [("defer", {"melRef": "MEL 24-11 CAT B - IDG change planned at base"})]),
    ("ZS-LEC", "A320", "36", "FAPE", "DEFERRAL",
     "ENG 2 bleed trips off on overtemp during ground ops on hot days, remains on in flight, second month of this pattern",
     [("defer", {"melRef": "MEL 36-11 CAT B"})]),
    ("ZS-LED", "A320", "27", "FAOR", "DEFERRAL",
     "F/CTL ELAC 1 FAULT in cruise, control normal on ELAC 2",
     [("defer", {"melRef": "MEL 27-93 CAT B"})]),
    ("ZS-LED", "A320", "28", "FACT", "OBSERVATION",
     "Total FQI disagrees with uplift plus previous total by approx 600 kg after refuel, wing quantities balanced, small discrepancies all week",
     []),
    ("ZS-LEE", "A320", "49", "FAOR", "DEFERRAL",
     "APU protective shutdown NO FLAME on two start attempts, fuel pressure normal per ECAM APU page",
     [("defer", {"melRef": "MEL 49-10 CAT C - APU inop"})]),
    ("ZS-LEF", "A320", "21", "FALE", "OBSERVATION",
     "Repeated passenger ear-discomfort complaints on descent with this airframe, pressurisation indications normal each time",
     []),
    ("ZS-LEG", "A320", "22", "FAOR", "DEFERRAL",
     "A/THR disconnects uncommanded 3 times in cruise, re-engages normally each time, thrust lever 1 instinctive switch suspect",
     [("defer", {"melRef": "MEL 22-30 CAT B"})]),
    ("ZS-LEH", "A320", "29", "FACT", "DEFERRAL",
     "HYD G RSVR LO LVL third time in 10 days, quantity drops approx 2 litres per day, no external leak found after two inspections",
     [("defer", {"melRef": "MEL 29-10 CAT B - leak measurement test at base"})]),
    ("ZS-LEI", "A320", "32", "FAOR", "OBSERVATION",
     "Brake wear indicator pin flush on No 4 brake at transit check, remaining brakes healthy",
     []),
    ("ZS-LEJ", "A320", "26", "FAGG", "DEFERRAL",
     "LAV SMOKE DET FAULT fwd lavatory, recurring after detector change, CIDS-SDF channel suspect",
     [("defer", {"melRef": "MEL 26-15 CAT C"})]),
    ("ZS-LEK", "A320", "28", "FAOR", "DEFERRAL",
     "Outer cell fuel trapped, inner cell emptied and engines fed normally, outer quantity never decreases, intercell transfer valve failed closed",
     [("rectify", {"rectificationNote": "Intercell transfer valve motor replaced, transfer test satisfactory both directions"})]),
    ("ZS-LEL", "A320", "27", "FALE", "DEFERRAL",
     "Slats slow to extend on one side during approach configuration, completed normally, no fault message",
     [("defer", {"melRef": "MEL 27-80 CAT C - monitor"}),
      ("rectify", {"rectificationNote": "Slat drive torque check satisfactory, lubrication per AMM, ops test normal"}),
      ("close", {})]),
    ("ZS-LEM", "A320", "24", "FABL", "OBSERVATION",
     "Class 2 message IDG COOLER on post-flight report, all temperatures normal, third occurrence this month",
     [("rectify", {"rectificationNote": "Fuel/oil cooler and recirculation valve function checks satisfactory, temps normal over 3 sectors"}),
      ("close", {})]),
    ("ZS-LEN", "A320", "36", "FAOR", "DEFERRAL",
     "Bleed pressure low at idle and during taxi, packs weak on ground, pressure normal at cruise power, HP valve suspect",
     [("defer", {"melRef": "MEL 36-12 CAT B"}),
      ("rectify", {"rectificationNote": "HP valve replaced, bleed pressure normal at idle and take-off power"})]),
    ("ZS-LEO", "A320", "49", "FAUP", "DEFERRAL",
     "APU will not start, FLAP NOT OPEN code, intake flap found closed with actuator unpowered",
     [("defer", {"melRef": "MEL 49-21 CAT C - APU inop"})]),
    ("ZS-LEP", "A320", "22", "FAOR", "OBSERVATION",
     "MCDU 2 screen frozen on PERF page during turnaround, MCDU 1 normal",
     []),
    # ZS-LEQ, ZS-LER, ZS-LES, ZS-LET: in service, no defects. A clean tail
    # is a data point too.
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
