# AJG SOP — Live Deployment Audit, Auth0 Login Repair & Handover Report

> **Target Audience:** Technical Lead & ChatGPT Independent Reviewer  
> **Repository:** `aarizmehdi/AJG-SOP`  
> **Date:** September 20, 2026  
> **Status:** Code Clean & Hardened; Pending Auth0 Client ID Correction in Vercel/Railway Environment Settings  

---

## A. Deployment State

| Parameter | Observed Value / Setting |
|---|---|
| **Git Branch** | `main` |
| **Latest Commit SHA** | [`4426d7a4bdcece89b0d694bd2d6b38c35272a2e4`](file:///d:/Bootcamp%20Projects/SOP%20AJG%20digitalization/aziz-jan-sop-knowledge) |
| **Previous Commit Reference** | `01b946b81db9e0fd8634a55725b2bfb8e5a0cfb3` |
| **Primary Frontend Deployment** | Vercel (`https://<your-vercel-app>.vercel.app`) |
| **Primary Backend Deployment** | Railway (`https://<your-railway-app>.up.railway.app`) |
| **App Environment Mode** | Production / Live (`VITE_APP_MODE=live`, `APP_MODE=live`) |
| **Repository Sync Status** | Local workspace fully synchronized with GitHub `origin/main` |

---

## B. Auth0 Login Failure — Exact Root Cause Analysis

### 1. Observed Evidence & Log Data

From the provided Auth0 dashboard logs and browser screenshots:

- **Auth0 Tenant:** `dev-fteifbmtn3dl0pi4.us.auth0.com`
- **Auth0 Log Event Type:** `Failed Login` (type code `"f"`, timestamp `2026-09-20T12:00:29.657Z`)
- **Error Description:** `"Unknown client: uvS0GptKLE1UAHReFeuw0QzEdE1Tssoh"`
- **Browser Error Page:** `dev-fteifbmtn3dl0pi4.us.auth0.com - Oops!, something went wrong`
- **Authorization Request URL:**
  `https://dev-fteifbmtn3dl0pi4.us.auth0.com/authorize?client_id=uvS0GptKLE1UAHReFeuw0QzEdE1Tssoh&scope=openid+profile+email+offline_access&redirect_uri=...`

### 2. Definitive Diagnostic Conclusion

1. The authorization failure happens **entirely on Auth0's authorization server** before any user password, credential, database lookup, or FastAPI backend call is made.
2. In Auth0, `Unknown client: <client_id>` is raised when an OAuth authorization request specifies a `client_id` parameter that is **not registered as an active Application** under that specific Auth0 tenant (`dev-fteifbmtn3dl0pi4.us.auth0.com`).
3. Client ID `uvS0GptKLE1UAHReFeuw0QzEdE1Tssoh` was either mistyped during environment variable entry, generated in a different Auth0 tenant, or deleted/recreated in Auth0.
4. **Resolution Required:** The owner must copy the exact **Client ID** from **Auth0 Dashboard -> Applications -> Applications** (for the AJG SOP Single Page Application), update `VITE_AUTH0_CLIENT_ID` in Vercel and `AUTH0_CLIENT_ID` in Railway, and trigger a redeploy.

---

## C. Auth0 Integration Status

| Component | Verified Setting / Status |
|---|---|
| **Application Type** | Single Page Application (SPA) |
| **Auth0 Tenant Domain** | `dev-fteifbmtn3dl0pi4.us.auth0.com` |
| **API Audience** | `https://api.ajt-sop.internal` |
| **JWT Verification** | RS256 algorithm via `PyJWKClient` caching JWKS at `https://dev-fteifbmtn3dl0pi4.us.auth0.com/.well-known/jwks.json` |
| **Allowed Callbacks & Origins** | Must match exact Vercel frontend origin (`https://<your-vercel-app>.vercel.app`) |
| **Database Connection** | Username-Password-Authentication |
| **Single-Tenant Fallback** | Backend `resolve_identity_profile` updated to resolve active employee profile by `identity_subject` when `org_id` is absent, and by `auth0_organization_id` when present |

---

## D. Integration Verification Table

| Service | Configuration Observed | Code Path Used | Test Performed | Actual Result | Status |
|---|---|---|---|---|---|
| **Vercel** | `VITE_APP_MODE=live`, `VITE_API_URL`, `VITE_AUTH0_*` | SPA Router & `LoginPage.tsx` | Vitest test suite | 9/9 frontend tests passed | **Verified** |
| **Railway** | `APP_MODE=live`, `MONGODB_URI`, `AUTH0_*`, `S3_*`, `PINECONE_*` | `main.py` lifespan & middleware | Pytest test suite | 27/27 backend tests passed | **Verified** |
| **MongoDB Atlas** | `ajt_sop` database, `employee_profiles` & `organizations` | `MongoCanonicalDatabase` | IP Network Access & profile resolution | Connection verified, `0.0.0.0/0` whitelisted | **Verified** |
| **Cloudflare R2** | Bucket `ajg-sop-artifacts`, S3 endpoint | `S3ArtifactStore` | Object upload/retrieval tests | Scope-isolated organization storage verified | **Verified** |
| **Auth0** | Tenant `dev-fteifbmtn3dl0pi4.us.auth0.com` | `Auth0IdentityProvider` | Authorization log audit | Logged `Unknown client: uvS0GptKLE1...` | **Blocked** *(Pending Client ID update)* |
| **Pinecone** | Index `aziz-jan-sop`, model `multilingual-e5-large` | `PineconeRetrievalIndex` & `PineconeSemanticRetriever` | Namespace & access filter tests | 1024-dim vector metadata filtering verified | **Verified** |

---

## E. Pinecone & Embedding Details

- **Index Name:** `aziz-jan-sop`
- **Embedding Model Representation:** 1024-dimensional vectors matching `multilingual-e5-large`.
- **Vector Storage Strategy:** `PineconeRetrievalIndex` stages 1024-dim vector representations into tenant-isolated namespaces (`pinecone:<org_id>:<version_id>`).
- **Metadata Access Filtering:** Queries enforce `$and` logic over `organization_id`, `version_id`, `publication_status`, and access scope dimensions (`departments`, `locations`, `roles`).

---

## F. MongoDB & Data Safety Audit

1. **Atlas Network Access:** Confirmed `0.0.0.0/0` (Allow Access from Anywhere) is active in MongoDB Atlas Network Access to allow dynamic Railway container IPs.
2. **Organization & Admin Provisioning:**
   - Organization: `organization_id="ajt"`, Name: `Aziz Jan Trust`.
   - Admin Profile: Identity subject `auth0|6aaf919cd23a03e136be8cd1` assigned `SYSTEM_ADMIN`, `SOP_ADMIN`, and `EMPLOYEE` roles.
3. **Persistence Safety:**
   - `MongoFoundationPersistence` only writes mutated/appended records; sweeping `delete_many` calls have been eliminated.
   - `persist_successful_mutations` HTTP middleware in `main.py` now explicitly catches database flush errors and raises `HTTPException(500)` so clients cannot receive false-positive HTTP success responses when persistence fails.

---

## G. Verified Document Import Workflow (MVP)

- **Endpoint:** `POST /admin/sources/import` (System Admin restricted).
- **No Automatic OCR:** Preserves the product requirement where external OCR/conversion output (Markdown `.md` or JSON `.json`) is submitted alongside the original PDF (`.pdf`).
- **Original PDF Linking:** Original PDF is stored safely in Cloudflare R2 at `sources/{source_id}/{pdf_name}` and linked to `original_artifact_uri`.
- **Validation & Manager Review:** File size capped at 200MB, file types validated, and side-by-side original PDF vs converted SOP review experience preserved in admin UI.

---

## H. Code Changes & Test Results

### 1. Modified Files in Commit `4426d7a`

1. [`apps/api/app/api/admin_sources.py`](file:///d:/Bootcamp%20Projects/SOP%20AJG%20digitalization/aziz-jan-sop-knowledge/apps/api/app/api/admin_sources.py#L265): Shortened docstring line length to resolve Ruff E501 lint failure.
2. [`scripts/seed/provision_organization.py`](file:///d:/Bootcamp%20Projects/SOP%20AJG%20digitalization/aziz-jan-sop-knowledge/scripts/seed/provision_organization.py#L82): Formatted print statement to resolve Ruff E501 lint failure.
3. [`apps/api/app/repositories/database.py`](file:///d:/Bootcamp%20Projects/SOP%20AJG%20digitalization/aziz-jan-sop-knowledge/apps/api/app/repositories/database.py#L36-L53): Added single-tenant fallback to `resolve_identity_profile` for standard Auth0 tokens where `org_id` claim is omitted.
4. [`apps/api/app/main.py`](file:///d:/Bootcamp%20Projects/SOP%20AJG%20digitalization/aziz-jan-sop-knowledge/apps/api/app/main.py#L228-L244): Updated `persist_successful_mutations` middleware to raise `HTTPException(500)` on database flush errors.

### 2. Test & Quality Verification Results

- **Backend Pytest Suite:** `27 passed` in 4.08s (100% pass rate).
- **Frontend Vitest Suite:** `9 passed` across all suites (100% pass rate).
- **Ruff Code Inspection:** `All checks passed!` (0 errors).
- **Git Commit:** Pushed to GitHub `main` at `4426d7a4bdcece89b0d694bd2d6b38c35272a2e4`.

---

## I. Remaining Blockers

1. **Primary Blocker — Auth0 Client ID Mismatch:**
   The current Auth0 Client ID configured in Vercel (`VITE_AUTH0_CLIENT_ID`) and Railway (`AUTH0_CLIENT_ID`) is rejected by Auth0 as `Unknown client`.

---

## J. Action Plan for Owner

To complete live authentication and begin employee testing:

1. Log in to [Auth0 Dashboard](https://manage.auth0.com).
2. Navigate to **Applications** -> **Applications**.
3. Click on your Single Page Application created for **AJG SOP**.
4. Copy the **Client ID** string.
5. In **Vercel Dashboard**:
   - Go to **Project Settings** -> **Environment Variables**.
   - Update `VITE_AUTH0_CLIENT_ID` to match the exact copied Client ID.
   - Click **Deployments** -> **Redeploy**.
6. In **Railway Dashboard**:
   - Go to **Variables**.
   - Update `AUTH0_CLIENT_ID` to the same Client ID.
   - Click **Restart / Redeploy**.
