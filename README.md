# TechLog Cloud — Digital Aircraft Technical Log

A serverless aircraft technical log on AWS: line mechanics raise defects, certifying staff defer / rectify / close them under a strict workflow, and planning sees the fleet live — with an append-only audit history modelled on Part 145 record-keeping.

Built by **Lebogang Sethibe** — 20+ years aircraft maintenance (B737-800, A320 family, A330/A340, A350, A380, B777) — as portfolio project 1 of 3 in aviation cloud engineering. **All data is synthetic.** No real airline, aircraft or person appears anywhere in this repo.

## Live demo

**▶ https://d3qpkw8em0knl8.cloudfront.net** — deployed to **af-south-1 (Cape Town)** and verified end-to-end on 22 Oct 2026: role-based sign-in (Mechanic / Certifying), fleet board, the full `OPEN → DEFERRED → RECTIFIED → CLOSED` workflow with append-only audit history, and a live AOG email alert via SNS. Demo logins available on request.

## Why

Paper and deferred-defect systems fail in predictable ways: a defect raised at an outstation isn't visible to planning until the aircraft lands, handwriting gets misread, and repeat defects hide across log pages. TechLog Cloud is the same technical log, rebuilt the way the data wants to work — live, searchable, and impossible to quietly edit.

## Features

- Raise a defect in three required fields (tail, ATA chapter, description) — designed for a line station at 03:00
- Workflow enforced in code: `OPEN → DEFERRED (MEL ref required) → RECTIFIED (note required) → CLOSED`, reopen with reason; a DEFERRED defect cannot be closed without rectification
- **AOG defects fire an SNS alert immediately**
- Defect photos via S3 pre-signed upload into a **versioned bucket with Object Lock** (retention story)
- Append-only audit history per defect — every state change, who did it, when, and the MEL ref / rectification note
- Role-based access: Cognito groups `Mechanic` (raise) and `Certifying` (raise + status changes), enforced at the API authorizer *and* in the Lambda
- Fleet board by status + per-tail log page view
- 15 unit tests covering validation, the workflow state machine, and the DynamoDB item shapes

## Architecture

```
CloudFront → S3 (static frontend, vanilla JS)
Browser ──Cognito JWT──▶ API Gateway (HTTP API, Cognito authorizer)
                              │
                              ▼
                     Lambda (Python 3.12, arm64)
                       │            │            │
                 DynamoDB        S3 docs      SNS (AOG alerts)
              (single table,   (versioned +
               GSI on status,   Object Lock)
               PITR enabled)
```

Full data model, access patterns and design trade-offs: **[DESIGN.md](DESIGN.md)**

Deployed to **af-south-1 (Cape Town)** — data residency aligned to POPIA.

## Tech

AWS SAM · Lambda (Python 3.12) · API Gateway HTTP API · DynamoDB (single-table, on-demand) · Cognito · S3 + CloudFront · SNS · CloudWatch · boto3 (runtime-provided, zero packaged dependencies)

## Run the tests

```bash
python3 -m unittest discover tests -v
```

The domain logic (`src/logic.py`) has no AWS imports by design — every rule is testable offline.

## Deploy

See **[DEPLOY.md](DEPLOY.md)** — full walkthrough for Windows + PowerShell: install AWS CLI + SAM CLI, `sam build`, `sam deploy --guided`, create the two demo users, load the synthetic seed data.

## Sample data

```bash
python3 scripts/generate_seed.py         # writes scripts/seed.json (10 defects)
python3 scripts/generate_seed.py --load  # also loads them into your table
```

The 10 seed defects are written from generic maintenance experience across both fleets — an AOG nose-gear steering defect, MEL deferrals, a closed hydraulic observation, cabin defects — in mixed workflow states so the fleet board demos properly.

## Part 145 record-keeping considerations (design notes)

- History items are **append-only**: the API exposes no update or delete path for them.
- The documents bucket uses Versioning + Object Lock so an uploaded defect photo cannot be silently replaced.
- DynamoDB Point-in-Time Recovery is on.
- **Honest limitation:** a production Part 145 electronic tech log needs attributable electronic signatures and regulator-accepted record retention. This demo's answer is Cognito identity on every action + the immutable history — the right shape, not a certified system. Stated plainly because pretending otherwise would fail the first quality-manager interview question.

## Known MVP trade-offs

- Log-page-per-tail uses a filtered Scan. Fine at demo scale; the production fix (GSI on `tail`) is one template change — see DESIGN.md.
- Frontend auth uses Cognito's USER_PASSWORD_AUTH flow directly (no SDK) to keep the frontend build-free.

## Cost (demo traffic, af-south-1)

Lambda / DynamoDB / API Gateway sit inside always-free or near-zero usage at demo scale; S3 + CloudFront are cents. Expected total: **< $2/month**, and everything is tagged `Project=TechLog` for Cost Explorer. Tear down any time with `sam delete`.

## Roadmap (stretch)

QR code on the aircraft opening a pre-filled raise form · offline-tolerant form for hangar dead spots · feed defect data into **Repeat Defect Radar** (portfolio project 2 — reliability analytics with S3 + Athena).
