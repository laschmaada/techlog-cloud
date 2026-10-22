# TechLog Cloud v1 → v2 upgrade (Highveld Air)

v2 = the fictional **Highveld Air** brand, an A320-only fleet (ZS-LEA – ZS-LET),
self-service account registration, and a TTM-grounded seed set. The stack
updates **in place** — same API URL, same CloudFront URL, same Cognito pool,
same demo users. Only the table data is reset and reseeded.

Run everything from `D:\DevOps\techlog-cloud` in PowerShell, with the
profile set: `$env:AWS_PROFILE="cognexion-admin"`.

## 1. Update the code

Unzip `techlog-cloud-v2.zip` over the existing project folder (overwrite).
Your `samconfig.toml` and `frontend\config.js` are **not** in the zip and
stay untouched.

## 2. Build and deploy (in-place update)

```powershell
sam build
sam deploy
```

Review the changeset before confirming: expect the UserPool modified
(LambdaConfig + AdminCreateUserConfig), and 2 adds (PostConfirmationFunction,
PostConfirmationInvokePermission). **If the changeset ever shows the UserPool
being REPLACED, stop and say no** — that would orphan the demo users; it is
not expected for this change.

After deploy, check the Outputs: `UserPoolId`, `UserPoolClientId` and the
API / frontend URLs should be identical to v1 (no config.js change needed).

## 3. Publish the new frontend

```powershell
aws s3 sync frontend s3://techlog-cloud-frontendbucket-340zquuk0r9y --exclude config.example.js --delete
```

(config.js is already in the bucket from v1 with the right values; the sync
keeps it because it also exists locally.)

## 4. Reset the data and load the Highveld Air seed

```powershell
$env:TABLE_NAME="techlog-cloud-TechLogTable-1HD53JYG5KYMP"
python scripts\reset_data.py        # deletes the old ZS-SX*/ZS-ZW* demo data
python scripts\generate_seed.py --load
```

## 5. Verify (5 minutes)

1. Open https://d3qpkw8em0knl8.cloudfront.net (hard-refresh: Ctrl+F5).
   You should see the navy/gold Highveld Air sign-in page.
2. Sign in as mechanic@demo.local — fleet grid shows 20 tails, stats read
   18/20 in service, 6 open, 2 AOG, 10 deferred.
3. Create a brand-new account (Create account tab) with a real email you
   control → enter the emailed code → sign in. Top bar should show
   **Mechanic** and you can raise a defect (Certifying actions will
   correctly refuse).
4. Raise a test AOG defect → the SNS alert email still arrives at
   info@cognexion.co.za (→ connexion3005@gmail.com).
