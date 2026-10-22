# TechLog Cloud — Deploy Guide (Windows / PowerShell)

Verified against AWS's own SAM documentation on 2026-10-22: AWS's docs confirm the first deploy uses `sam deploy --guided` and the guided flow asks for stack name, region, change confirmation, IAM role creation, and saving your answers to `samconfig.toml`. Steps that happen inside the AWS Console are marked **UNVERIFIED** (click-paths change; the CLI commands given instead are the reliable route).

Budget ±45 minutes for the first run. Everything deploys into **af-south-1 (Cape Town)**.

---

## 0. Before you start

- Work as your IAM admin user **`cognexion-admin`** — never root.
- You need an **access key for the AWS CLI** on that user. **UNVERIFIED click-path:** AWS Console → IAM → Users → `cognexion-admin` → Security credentials → Create access key → use case "Command Line Interface (CLI)". Save the key ID and secret somewhere safe (not in this repo, not in chat).

## 1. Install the tools

From AWS's official download pages (search "AWS CLI v2 Windows installer" and "AWS SAM CLI Windows installer" on aws.amazon.com — both are 64-bit MSI installers):

1. Install **AWS CLI v2** (MSI).
2. Install **AWS SAM CLI** (MSI).
3. Open a **new** PowerShell window and verify:

```powershell
aws --version
sam --version
```

## 2. Configure credentials

```powershell
aws configure --profile cognexion-admin
```

Enter the access key from step 0, then:

- Default region name: `af-south-1`
- Default output format: `json`

In every command below, add `--profile cognexion-admin` (or set `$env:AWS_PROFILE="cognexion-admin"` once per window).

## 3. Build and deploy

From the project root (where `template.yaml` lives):

```powershell
sam build
sam deploy --guided
```

Guided answers:

| Prompt | Answer |
|---|---|
| Stack Name | `techlog-cloud` |
| AWS Region | `af-south-1` |
| Parameter AlertEmail | *your email* (you'll get AOG alerts here) |
| Confirm changes before deploy | `Y` — review the list, then deploy `Y` |
| Allow SAM CLI IAM role creation | `Y` |
| Disable rollback | `N` |
| Save arguments to configuration file | `Y` |

Deploy takes a few minutes. Afterwards SAM prints **Outputs** — keep that window open, you need: `ApiUrl`, `FrontendBucketName`, `FrontendUrl`, `UserPoolId`, `UserPoolClientId`.

**Check your email** and confirm the SNS subscription (one click) or AOG alerts won't send.

## 4. Create the demo users (CLI)

```powershell
$pool = "<UserPoolId from Outputs>"

# Mechanic (can raise defects)
aws cognito-idp admin-create-user --user-pool-id $pool --username mechanic@demo.local --user-attributes Name=email,Value=mechanic@demo.local Name=email_verified,Value=true --message-action SUPPRESS
aws cognito-idp admin-set-user-password --user-pool-id $pool --username mechanic@demo.local --password "<choose a strong password>" --permanent
aws cognito-idp admin-add-user-to-group --user-pool-id $pool --username mechanic@demo.local --group-name Mechanic

# Certifying (can also defer / rectify / close)
aws cognito-idp admin-create-user --user-pool-id $pool --username certifying@demo.local --user-attributes Name=email,Value=certifying@demo.local Name=email_verified,Value=true --message-action SUPPRESS
aws cognito-idp admin-set-user-password --user-pool-id $pool --username certifying@demo.local --password "<choose a strong password>" --permanent
aws cognito-idp admin-add-user-to-group --user-pool-id $pool --username certifying@demo.local --group-name Certifying
```

## 5. Configure and upload the frontend

1. Copy `frontend\config.example.js` to `frontend\config.js` and fill in `API_BASE`, `USER_POOL_ID`, `USER_POOL_CLIENT_ID` from the Outputs (region is already `af-south-1`).
2. Upload:

```powershell
aws s3 sync frontend/ s3://<FrontendBucketName>/
```

3. Open `<FrontendUrl>` in your browser.

## 6. Load the synthetic seed data

Needs Python 3 and boto3 on your PC: `pip install boto3`

```powershell
aws dynamodb list-tables --query "TableNames[?contains(@,'TechLog')]"
$env:TABLE_NAME = "<the table name from that list>"
python scripts/generate_seed.py --load
```

## 7. Test the flow (5 minutes)

1. Sign in as **mechanic@demo.local** → raise an AOG defect → check your email for the SNS alert.
2. Sign out, sign in as **certifying@demo.local** → open the defect → Defer it (MEL ref required) → Rectify → Close. Watch the audit history grow at every step.
3. Back as mechanic, try to change a status — there are no action buttons for state changes your role can't make, and the API itself returns 403 for status changes from a Mechanic token.

## 8. Costs and teardown

- Everything is tagged `Project=TechLog`. AWS Console → Cost Explorer → filter by that tag to see the real number (expect < $2/month at demo use). **UNVERIFIED click-path** — Cost Explorer layout changes often; the tag filter is the part that matters.
- Your `My Zero-Spend Budget` alert remains the safety net.
- Full teardown: `sam delete` (type the stack name `techlog-cloud` to confirm). Note: the documents bucket must be emptied before the stack can delete it.

## Troubleshooting

- **`sam build` fails on Python version** — the template targets Python 3.12; if your PC has a different Python, `sam build --use-container` builds in Docker instead (needs Docker Desktop running).
- **Login fails with "User does not exist"** — the user was created in a different region's pool. Check `aws configure` region is `af-south-1` in every command.
- **Frontend loads but API calls 401** — `config.js` values don't match the Outputs, or the browser cached the old file: re-run the `aws s3 sync` and hard-refresh (Ctrl+F5).
