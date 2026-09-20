# AJG SOP — Live Deployment Audit, Auth0 Login Repair & Handover Report

> **Target Audience:** Principal Engineer & ChatGPT Independent Reviewer  
> **Repository:** `aarizmehdi/AJG-SOP`  
> **Date:** September 20, 2026  
> **Status:** Code Clean & Hardened; CORS & Auth Token Persistence Verified; All CI Checks Passing  

---

## A. Deployment State

| Parameter | Observed Value / Setting |
|---|---|
| **Git Branch** | `main` |
| **Latest Commit SHA** | [`b65810fe158ea9cbb0fe697fbfb264906f2df792`](file:///d:/Bootcamp%20Projects/SOP%20AJG%20digitalization/aziz-jan-sop-knowledge) |
| **Primary Frontend Deployment** | Vercel (`https://ajg-sop-web.vercel.app`) |
| **Primary Backend Deployment** | Railway (`https://<your-railway-app>.up.railway.app`) |
| **App Environment Mode** | Production / Live (`VITE_APP_MODE=live`, `APP_MODE=live`) |
| **Repository Sync Status** | Local workspace fully synchronized with GitHub `origin/main` |

---

## B. Auth0 Login & API Access Audit — Root Cause & Resolution

### 1. Root Cause Analysis

- **Initial Symptom (Resolved):** User authenticates on Auth0, browser redirects to Vercel, workspace skeleton briefly flashes, then immediately bounces back to `/login`.
  - **Cause:** `Auth0Provider` used `cacheLocation="memory"`. In `onRedirectCallback`, `window.location.href = target` forced a full browser reload, wiping in-memory tokens.
  - **Fix:** Changed `cacheLocation` to `"localstorage"` in `providers.tsx` and used clean SPA history replacement.

- **Secondary Symptom — `(Failed to fetch)` (Resolved):**
  - **Cause:** Browser preflight `fetch()` to Railway backend failed when `WEB_ORIGIN` lacked trailing slash variants or differed from the exact Vercel deployment URL.
  - **Fix:** Updated `config.py` to normalize trailing slashes in `allowed_origins` and added `allow_origin_regex=r"https://.*\.vercel\.app"` to `CORSMiddleware` in `main.py`.

---

## C. Post-Login Destination & Role-Based Access Control (RBAC) Matrix

| Application Role | Navigation Bar Items | Allowed Frontend Routes | Forbidden Actions / Routes | Backend Enforcement |
|---|---|---|---|---|
| **Employee** | Home, Search, Assistant | `/home`, `/search`, `/assistant`, `/policies/:id`, `/language` | Direct access to `/admin/*` renders "Administration Required" ErrorState | FastAPI `/admin/*` endpoints return `403 Forbidden` (`require_admin`) |
| **SOP Admin / Dept Manager** | Home, Search, Assistant, Policy Library | `/home`, `/search`, `/assistant`, `/policies/:id`, `/language`, `/admin/policies`, `/admin/review-queue`, `/admin/workflow/:id`, `/admin/review/:id` | `+ Add SOP` button hidden; direct access to `/admin/add` renders "System Administrator Required" ErrorState | FastAPI `/admin/sources/upload`, `/admin/sources/paste`, `/admin/sources/import` return `403 Forbidden` (`require_system_admin`) |
| **System Admin** | Home, Search, Assistant, Policy Library (+ Add SOP button) | All routes including `/admin/add`, `/admin/sources/capabilities`, review and publication workflows | N/A (Full administrative authority) | Authorized across all endpoints |

---

## D. Automated Quality & CI Results

- **Frontend Vitest Suite:** `9 passed` across 7 test files (100%).
- **Prettier Format Check (`npm run format:check`):** `All matched files use Prettier code style!` (0 errors).
- **Backend Pytest Suite:** `27 passed` (100%).
- **Ruff Code Inspection:** `All checks passed!` (0 errors).
- **Git Commit:** Pushed to GitHub `main` at `b65810fe158ea9cbb0fe697fbfb264906f2df792`.
