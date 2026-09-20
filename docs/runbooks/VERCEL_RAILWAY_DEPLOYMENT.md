# Vercel and Railway deployment

Deploy the React application in `apps/web` to Vercel and the repository `Dockerfile` to Railway. MongoDB Atlas is canonical storage, Cloudflare R2 holds private source artifacts, and Pinecone remains derived retrieval data.

The current authentication and environment cutover procedure is [FIREBASE_CUTOVER.md](FIREBASE_CUTOVER.md). Follow it in order: configure Firebase, deploy the backend, link the exact existing administrator profile, deploy the frontend, perform the real profile request, and only then remove the obsolete Auth0 variables from the hosting platforms.

Railway health checking uses `/health`. That endpoint proves process availability only. Release verification requires an authenticated `GET /api/v1/profile/me`, followed by role-appropriate SOP operations.

Vercel must build from the repository root with the workspace scripts, or use `apps/web` as its root directory. The SPA rewrite in `apps/web/vercel.json` keeps protected routes addressable after refresh.

Production CORS must include the exact Vercel production origin in `WEB_ORIGIN`. Temporary preview origins belong in `CORS_ORIGINS`. The API also accepts HTTPS Vercel preview subdomains, but the explicit production origin remains required for configuration validation and audit clarity.
