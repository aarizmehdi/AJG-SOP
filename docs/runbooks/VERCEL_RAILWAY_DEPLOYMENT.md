# Vercel + Railway Deployment Runbook — AJG SOP Platform

**Customer:** Aziz Jan Trust (AJT)  
**Repository:** `aarizmehdi/AJG-SOP`  
**Frontend Deployment:** Vercel  
**Backend Deployment:** Railway  
**Target Database:** MongoDB Atlas  
**Target Object Store:** Cloudflare R2  

---

## 1. Architecture Overview

```
                      ┌──────────────────────┐
                      │    Vercel Frontend   │
                      │  (React 19 + Vite)   │
                      └──────────┬───────────┘
                                 │ HTTP/REST (Bearer Token)
                                 ▼
                      ┌──────────────────────┐
                      │    Railway Backend   │
                      │  (FastAPI / Python)  │
                      └────┬──────┬──────┬───┘
                           │      │      │
           ┌───────────────┘      │      └──────────────┐
           ▼                      ▼                     ▼
┌────────────────────┐ ┌────────────────────┐ ┌───────────────────┐
│   MongoDB Atlas    │ │   Cloudflare R2    │ │     Auth0 SSO     │
│ (Canonical DB +    │ │  (Original PDFs    │ │  (JWT Validation  │
│ Foundation Store)  │ │   & Artifacts)     │ │   & Management)   │
└────────────────────┘ └────────────────────┘ └───────────────────┘
```

---

## 2. Pre-Deployment Step-by-Step Instructions

### Step 2.1: GitHub Repository Settings (Manual)
1. **Set Default Branch to `main`:**
   - Go to GitHub Repository → **Settings** → **Branches**.
   - Ensure the Default branch is set to `main`.
2. **Branch Protection Rules:**
   - Enable Branch Protection for `main`:
     - Require pull request reviews before merging.
     - Require status checks to pass before merging (`web`, `api`, `docker`, `secrets`).

---

### Step 2.2: Auth0 Setup
1. **Create an Auth0 Application (Single Page Web Application):**
   - Name: `AJG SOP Web`
   - Allowed Callback URLs: `https://<your-vercel-domain>.vercel.app`
   - Allowed Logout URLs: `https://<your-vercel-domain>.vercel.app`
   - Allowed Web Origins: `https://<your-vercel-domain>.vercel.app`
   - Allowed Origins (CORS): `https://<your-vercel-domain>.vercel.app`
2. **Create an Auth0 API:**
   - Name: `AJG SOP API`
   - Identifier / Audience: `https://api.ajt-sop.internal`
   - Signing Algorithm: `RS256`
3. **Save Auth0 Credentials:**
   - `VITE_AUTH0_DOMAIN`: `your-tenant.us.auth0.com`
   - `VITE_AUTH0_CLIENT_ID`: `your-client-id`
   - `AUTH0_DOMAIN`: `your-tenant.us.auth0.com`
   - `AUTH0_AUDIENCE`: `https://api.ajt-sop.internal`

---

### Step 2.3: MongoDB Atlas Setup
1. **Create Cluster & Database:**
   - Cluster: Shared M0 or M10+ instance.
   - Database name: `ajt_sop`.
2. **Network Access:**
   - Allow Access from Anywhere (`0.0.0.0/0`) or configure Railway static IP.
3. **Database User:**
   - Create a user with ReadWrite privileges on `ajt_sop`.
4. **Connection String:**
   - Format: `mongodb+srv://<username>:<password>@<cluster>.mongodb.net/ajt_sop?retryWrites=true&w=majority`

---

### Step 2.4: Cloudflare R2 Setup
1. **Create Bucket:**
   - Bucket Name: `ajg-sop-artifacts`
2. **Generate R2 API Tokens:**
   - Go to R2 → **Manage R2 API Tokens** → **Create Token**.
   - Permissions: `Edit` (Read + Write).
3. **Save Credentials:**
   - `S3_BUCKET`: `ajg-sop-artifacts`
   - `S3_REGION`: `auto`
   - `S3_ENDPOINT_URL`: `https://<account_id>.r2.cloudflarestorage.com`
   - `S3_ACCESS_KEY`: `<access-key-id>`
   - `S3_SECRET_KEY`: `<secret-access-key>`

---

## 3. Backend Deployment on Railway

1. **Connect Repository:**
   - In Railway Dashboard, click **New Project** → **Deploy from GitHub repo** → select `aarizmehdi/AJG-SOP`.
2. **Configure Build Settings:**
   - Railway will automatically detect `railway.json` and use the root `Dockerfile`.
3. **Set Environment Variables in Railway:**
   ```env
   APP_MODE=live
   APP_ENV=production
   PORT=8000
   WEB_ORIGIN=https://<your-vercel-domain>.vercel.app
   CORS_ORIGINS=https://<your-vercel-domain>.vercel.app

   MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/ajt_sop?retryWrites=true&w=majority
   MONGODB_DATABASE=ajt_sop

   AUTH0_DOMAIN=your-tenant.us.auth0.com
   AUTH0_AUDIENCE=https://api.ajt-sop.internal

   S3_BUCKET=ajg-sop-artifacts
   S3_REGION=auto
   S3_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
   S3_ACCESS_KEY=<access-key>
   S3_SECRET_KEY=<secret-key>

   DEEPSEEK_API_KEY=<your-deepseek-api-key>
   # Optional: PINECONE_API_KEY, PINECONE_INDEX if vector search is active
   ```
4. **Deploy & Verify:**
   - Trigger deployment.
   - Test Health check: `GET https://<your-railway-url>.up.railway.app/health`
   - Expected response: `{"status":"ok","mode":"live","mongodb":true}`

---

## 4. Initial Organization Provisioning

Run the provisioning script to create the initial Aziz Jan Trust organization record and system admin profile in MongoDB:

```bash
uv run python -m scripts.seed.provision_organization \
  --mongo-uri "mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/ajt_sop?retryWrites=true&w=majority" \
  --org-id "ajt" \
  --org-name "Aziz Jan Trust" \
  --auth0-org-id "org_123456" \
  --admin-sub "auth0|<user-sub-id>" \
  --admin-email "admin@azizjantrust.org" \
  --admin-name "System Administrator" \
  --with-system-admin
```

---

## 5. Frontend Deployment on Vercel

1. **Import Project into Vercel:**
   - Vercel Dashboard → **Add New** → **Project** → Select `aarizmehdi/AJG-SOP`.
   - Root Directory: `apps/web` (or leave root and configure Root Directory = `apps/web`).
   - Framework Preset: `Vite`.
2. **Set Environment Variables in Vercel:**
   ```env
   VITE_APP_MODE=live
   VITE_API_URL=https://<your-railway-url>.up.railway.app/api/v1
   VITE_AUTH0_DOMAIN=your-tenant.us.auth0.com
   VITE_AUTH0_CLIENT_ID=<your-auth0-spa-client-id>
   VITE_AUTH0_AUDIENCE=https://api.ajt-sop.internal
   ```
3. **Deploy & Verify:**
   - Click **Deploy**.
   - Test loading the frontend URL. Refreshing sub-routes should work (backed by `vercel.json` SPA rewrite rule).

---

## 6. SOP Import Workflow (Controlled Import)

To import an externally verified PDF + Markdown/JSON source without requiring paid OCR:

1. Log in to the application as a user with `system_admin` role.
2. Call the controlled import API:
   ```bash
   curl -X POST "https://<your-railway-url>.up.railway.app/api/v1/admin/sources/import" \
     -H "Authorization: Bearer <auth0-jwt-token>" \
     -F "policy_id=policy-001" \
     -F "version_id=ver-001" \
     -F "original_file=@/path/to/original.pdf" \
     -F "structured_file=@/path/to/structured_content.md"
   ```
3. Navigate to the **Review UI** in the web application to inspect the side-by-side comparison of the original PDF and extracted canonical structure.
4. Save review → Approve structure → Index → Publish.

---

## 7. Owner Verification Checklist (Live Mode)

- [ ] **Health Check:** `GET /health` returns `status: ok` and `mongodb: true`.
- [ ] **Auth0 SSO:** Log in via frontend, verify JWT is accepted by backend.
- [ ] **Data Persistence:** Create draft policy version, modify, and verify MongoDB Atlas stores the document without deleting concurrent records.
- [ ] **PDF Artifact Storage:** Upload PDF via controlled import, verify file is placed in Cloudflare R2 bucket.
- [ ] **DeepSeek Q&A:** Ask assistant a question in English/Urdu/Roman Urdu and verify grounded answers with citations.
- [ ] **Forbidden Fixtures Guard:** Ensure no fixture login is permitted when `APP_MODE=live`.

---

## 8. Troubleshooting & Rollback

- **CORS Errors:** Verify `WEB_ORIGIN` in Railway matches the exact Vercel URL (including `https://`, no trailing slash).
- **Auth 401 Unauthorized:** Verify `AUTH0_AUDIENCE` in Railway backend matches `VITE_AUTH0_AUDIENCE` in Vercel frontend.
- **Rollback:** In Railway/Vercel dashboard, click **Rollback** on the deployment list to instantly revert to the previous working SHA.
