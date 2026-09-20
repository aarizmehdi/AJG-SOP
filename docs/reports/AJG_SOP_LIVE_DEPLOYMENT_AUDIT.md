# AJG SOP — Live Deployment Audit, Auth0 Login Repair & Handover Report

> **Target Audience:** Principal Engineer & ChatGPT Independent Reviewer  
> **Repository:** `aarizmehdi/AJG-SOP`  
> **Date:** September 20, 2026  
> **Status:** Root Cause Solved (`cacheLocation="localstorage"`); All CI Checks Passing  

---

## A. Deployment State

| Parameter | Observed Value / Setting |
|---|---|
| **Git Branch** | `main` |
| **Latest Commit SHA** | [`e7b4b434ff60b64be814e511fd3a5f4354c46fca`](file:///d:/Bootcamp%20Projects/SOP%20AJG%20digitalization/aziz-jan-sop-knowledge) |
| **Primary Frontend Deployment** | Vercel (`https://ajg-sop-web.vercel.app`) |
| **Primary Backend Deployment** | Railway (`https://<your-railway-app>.up.railway.app`) |
| **App Environment Mode** | Production / Live (`VITE_APP_MODE=live`, `APP_MODE=live`) |
| **Repository Sync Status** | Local workspace fully synchronized with GitHub `origin/main` |

---

## B. The Auth0 Token Memory Wipe Issue — Root Cause & Resolution

### 1. Root Cause Analysis

- **Observed Symptom:** User authenticates on Auth0, browser redirects to Vercel, workspace skeleton briefly flashes, then immediately bounces back to `/login`.
- **Underlying Root Cause:**
  1. `Auth0Provider` was configured with `cacheLocation="memory"`.
  2. When Auth0 redirected back to `https://ajg-sop-web.vercel.app/?code=...`, `onRedirectCallback` executed `window.location.href = target` to navigate to `/home`.
  3. `window.location.href` forced a full browser page reload, wiping the in-memory JavaScript cache where Auth0 stored tokens.
  4. Upon hard reload at `/home`, `@auth0/auth0-react` found zero tokens in memory, set `isAuthenticated = false`, and `AuthGuard` on `/home` bounced the browser back to `/login`.

### 2. Resolution Applied in Commit `e7b4b43`

1. **Persistent Token Storage:** Changed `cacheLocation="memory"` to `cacheLocation="localstorage"` in `providers.tsx`. Auth0 tokens now persist in browser `localStorage` across page reloads and navigations.
2. **Clean SPA Navigation:** Replaced `window.location.href` with `window.history.replaceState` in `onRedirectCallback`.
3. **No Reload Memory Wipe:** Authentication state survives intact; users land on `/home` cleanly without bouncing back to `/login`.

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
- **Git Commit:** Pushed to GitHub `main` at `e7b4b434ff60b64be814e511fd3a5f4354c46fca`.
