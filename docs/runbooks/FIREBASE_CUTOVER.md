# Firebase authentication cutover

This cutover keeps Firebase responsible for authentication and MongoDB responsible for all application authorization. A valid Firebase user receives no AJT access until its UID is explicitly linked to an active MongoDB employee profile.

## 1. Firebase console

Use Firebase project `ajg-sop-web`. Enable **Authentication → Sign-in method → Email/Password**. Add the production Vercel domain under Authentication authorized domains. Do not enable Firestore or Firebase Hosting.

The Firebase service-account JSON belongs only in Railway. Never paste it into chat, Vercel, source control, shell history, or a frontend variable.

## 2. Railway variables

Add these before deploying the Firebase branch:

```text
FIREBASE_PROJECT_ID=ajg-sop-web
FIREBASE_SERVICE_ACCOUNT_JSON=<complete regenerated JSON, stored directly as a private Railway variable>
```

Keep the existing `APP_MODE=live`, `MONGODB_URI`, `MONGODB_DATABASE`, private R2/S3, Pinecone, DeepSeek, `WEB_ORIGIN`, and `CORS_ORIGINS` values. `WEB_ORIGIN` must be the production Vercel origin; put any additional preview origins in `CORS_ORIGINS` as a comma-separated list.

After the Firebase deployment and real `/api/v1/profile/me` verification succeed, remove:

```text
AUTH0_DOMAIN
AUTH0_AUDIENCE
AUTH0_CLIENT_ID
```

## 3. Link the existing System Admin profile once

First identify the exact existing MongoDB profile `id`, `organization_id`, and current `identity_subject`. Do not select it by email. Run the command in a secure Railway one-off shell so `MONGODB_URI` remains an environment variable.

Dry run:

```bash
uv run python -m scripts.identity.link_firebase_uid \
  --mongo-uri "$MONGODB_URI" \
  --database "$MONGODB_DATABASE" \
  --organization-id "<EXACT_EXISTING_ORGANIZATION_ID>" \
  --profile-id "<EXACT_EXISTING_PROFILE_ID>" \
  --expected-current-subject "<EXACT_CURRENT_IDENTITY_SUBJECT>" \
  --firebase-uid "MpiZ3RClrrOHq43eiBaTe5tPKpR2" \
  --actor-id "firebase-cutover-owner"
```

Review the selected profile, then repeat the same command with `--apply`. The script runs the profile update and audit insert in one MongoDB transaction. It stops if the profile is absent, inactive, lacks the existing `system_admin` role, changed since inspection, or the Firebase UID belongs to another profile. It changes only `identity_subject`; the profile ID, organization, roles, scopes, and existing audit records remain intact.

## 4. Vercel variables

Add to Production and the intended Preview environments:

```text
VITE_APP_MODE=live
VITE_API_URL=https://ajg-sop-production.up.railway.app/api/v1
VITE_FIREBASE_API_KEY=<Firebase web app API key>
VITE_FIREBASE_AUTH_DOMAIN=ajg-sop-web.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=ajg-sop-web
VITE_FIREBASE_APP_ID=<Firebase web app ID>
```

After the real deployed login and profile request succeed, remove and redeploy without:

```text
VITE_AUTH0_DOMAIN
VITE_AUTH0_CLIENT_ID
VITE_AUTH0_AUDIENCE
```

## 5. Required deployed verification

1. Open the deployed `/login` page and sign in with the existing Firebase account.
2. In browser Network tools, confirm the request to `GET https://ajg-sop-production.up.railway.app/api/v1/profile/me` carries `Authorization: Bearer <Firebase ID token>` and returns `200`.
3. Confirm the response is the existing System Admin profile and organization.
4. Sign out, confirm user-specific query cache is cleared, then sign in with an unknown Firebase account and confirm `/profile/me` returns `403 No active membership`.
5. Refresh the protected page and verify the Firebase session initializes before the workspace renders.
6. Exercise policy library, search, assistant, ingestion, review, and publication according to the linked Mongo role.

Do not remove the current production Auth0 variables until steps 1–3 pass on the Firebase deployment. Keeping the old variables during the staged deployment is harmless because the Firebase code does not read them.

## 6. Railway connection evidence

The production API URL resolves and `/health` returns `200`. The unauthenticated `/api/v1/profile/me` returns the expected `401`. A live preflight from the current Vercel deployment origin with `authorization,content-type` now returns `200` with matching `Access-Control-Allow-Origin`, headers, and methods. The earlier browser `Failed to fetch` behavior was caused by the API rejecting the authorization preflight; commit `ceea1a3` broadened the allowed methods and headers. A real authenticated profile result still must be recorded during cutover because health and preflight checks do not prove identity-to-Mongo authorization.
