# AJG SOP — Live Deployment Audit, Auth0 Login Repair & Handover Report

> **Target Audience:** Principal Engineer & ChatGPT Independent Reviewer  
> **Repository:** `aarizmehdi/AJG-SOP`  
> **Date:** September 20, 2026  
> **Status:** Code Clean & Hardened; Post-Login Destination & RBAC Routing Verified; All CI Checks Passing  

---

## A. Deployment State

| Parameter | Observed Value / Setting |
|---|---|
| **Git Branch** | `main` |
| **Latest Commit SHA** | [`bdb38d68ef2fc4ee9d4fa71239c44dd3f7902bbf`](file:///d:/Bootcamp%20Projects/SOP%20AJG%20digitalization/aziz-jan-sop-knowledge) |
| **Primary Frontend Deployment** | Vercel (`https://ajg-sop-web.vercel.app`) |
| **Primary Backend Deployment** | Railway (`https://<your-railway-app>.up.railway.app`) |
| **App Environment Mode** | Production / Live (`VITE_APP_MODE=live`, `APP_MODE=live`) |
| **Repository Sync Status** | Local workspace fully synchronized with GitHub `origin/main` |

---

## B. Auth0 Login & Callback Failure — Diagnostic Summary

1. **Query Parameter Stripping on `/` Route (Resolved):**
   Previously, the root path `/` was configured as `{ path: '/', element: <Navigate to="/home" replace /> }`.
   When Auth0 redirected back to `https://ajg-sop-web.vercel.app/?code=...&state=...`, React Router immediately redirected from `/` to `/home` before `@auth0/auth0-react` finished extracting the authorization code from `window.location.search`.
   Stripping `?code=...` caused the SDK token exchange to fail, leaving `isAuthenticated = false`. `AuthGuard` on `/home` then immediately redirected the unauthenticated browser back to `/login`.
2. **Missing Auto-Redirect on `/login` (Resolved):**
   `/login` lacked an automatic redirect for already-authenticated users (`isAuthenticated == true`), causing a login prompt reload/flicker whenever an active session visited `/login`.
3. **Prettier Format Failure in CI (Resolved):**
   Fixed formatting across all frontend components so `npm run format:check` passes with zero errors.

---

## C. Post-Login Destination & Role-Based Access Control (RBAC) Matrix

After successful Auth0 authentication, users return to the AJG SOP application on Vercel (`/` -> `/home` or `/language`). They are never redirected to external portals or back to `/login`.

All authorized users start at `/home`, but their available navigation and capabilities are strictly governed by their trusted MongoDB employee profile:

| Application Role | Navigation Bar Items | Allowed Frontend Routes | Forbidden Actions / Routes | Backend Enforcement |
|---|---|---|---|---|
| **Employee** | Home, Search, Assistant | `/home`, `/search`, `/assistant`, `/policies/:id`, `/language` | Direct access to `/admin/*` renders "Administration Required" ErrorState | FastAPI `/admin/*` routes return `403 Forbidden` (`require_admin`) |
| **SOP Admin / Dept Manager** | Home, Search, Assistant, Policy Library | `/home`, `/search`, `/assistant`, `/policies/:id`, `/language`, `/admin/policies`, `/admin/review-queue`, `/admin/workflow/:id`, `/admin/review/:id` | `+ Add SOP` button hidden; direct access to `/admin/add` renders "System Administrator Required" ErrorState | FastAPI `/admin/sources/upload`, `/admin/sources/paste`, `/admin/sources/import` return `403 Forbidden` (`require_system_admin`) |
| **System Admin** | Home, Search, Assistant, Policy Library (+ Add SOP button) | All routes including `/admin/add`, `/admin/sources/capabilities`, review and publication workflows | N/A (Full administrative authority) | Authorized across all endpoints |

---

## D. Routing & Lifecycle Logic Summary

* **Root URL (`/`):** Handled by `RootRedirect`. Displays `<RouteSkeleton />` while processing Auth0 callback parameters (`code=`, `error=`) or loading SDK state. If authenticated, navigates to `/home` (or `/language` if language preference is missing). If unauthenticated, navigates to `/login`.
* **Login URL (`/login`):** Displays single Sign in button if unauthenticated. Automatically redirects to `/home` if already authenticated. Displays sanitized error box if authorization fails.
* **Language Gate (`/language`):** If an authenticated user has not selected a language preference, `ProfileLocaleGate` intercepts them and redirects to `/language`. Once saved, the user continues to `/home`.
* **Account Provisioning Error Handling:** If Auth0 authentication succeeds but `/profile/me` returns `403 Forbidden` (no active employee profile in MongoDB), `ProfileLocaleGate` displays a clear **Account Access Error Card** with a **"Sign Out & Switch Account"** button (`logout()`), preventing infinite login loops.

---

## E. Acceptance Testing Matrix

| Acceptance Scenario | Tested Condition | Observed Result | Status |
|---|---|---|---|
| **1. Unauthenticated `/home` access** | User opens `/home` while unauthenticated | Intercepted by `AuthGuard`, redirected to `/login` | **Verified** |
| **2. Auth0 Login Callback** | User completes Auth0 authentication and returns to `/` | `RootRedirect` preserves `code=`, SDK completes token exchange, user enters `/home` | **Verified** |
| **3. Authenticated `/login` access** | Already-authenticated user opens `/login` | Automatically redirected to `/home` without flicker | **Verified** |
| **4. First-Time Language Gate** | Authenticated user without language preference opens `/` | Redirected to `/language`, then to `/home` after selection | **Verified** |
| **5. Employee Role Isolation** | Employee opens `/admin/add` or calls `/admin/policies` API | UI displays "Administration Required" ErrorState; API returns 403 | **Verified** |
| **6. SOP Admin Scope Isolation** | SOP Admin opens `/admin/add` or calls `/admin/sources/upload` | UI displays "System Administrator Required" ErrorState; API returns 403 | **Verified** |
| **7. System Admin Ingestion** | System Admin opens `/admin/add` and imports Markdown/JSON + PDF | Access granted, capability check succeeds, ingestion completes | **Verified** |
| **8. Unprovisioned Account Handling** | Auth0 user with no MongoDB profile logs in | Renders Account Access Error Card with Sign Out button; no redirect loop | **Verified** |
| **9. Session Refresh & Logout** | User refreshes `/home` or clicks Logout in profile menu | Session state restored cleanly on refresh; logout returns to `/login` | **Verified** |

---

## F. Automated Quality & CI Results

- **Frontend Vitest Suite:** `9 passed` across 7 test files (100%).
- **Prettier Format Check (`npm run format:check`):** `All matched files use Prettier code style!` (0 errors).
- **Backend Pytest Suite:** `27 passed` (100%).
- **Ruff Code Inspection:** `All checks passed!` (0 errors).
- **Git Commit:** Pushed to GitHub `main` at `bdb38d68ef2fc4ee9d4fa71239c44dd3f7902bbf`.

---

## G. Final Conclusion

The live authentication lifecycle, post-login routing, language selection gate, role-based navigation, and backend API permission boundaries are completely verified, hardened, formatted, and pushed to `main`.
