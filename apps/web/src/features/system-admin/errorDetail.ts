import { ApiError } from '../../api/client';

const DEPLOYMENT_MISMATCH =
  'This API route is not available on the deployed backend. Deploy the backend revision that includes the System Admin control plane.';

export function systemAdminErrorDetail(
  error: unknown,
  fallback = 'The requested administration data could not be loaded.',
): string {
  if (!(error instanceof ApiError)) return fallback;

  if (error.status === 0)
    return 'The administration service could not be reached. Check the backend deployment and network connection.';
  if (error.status === 401)
    return 'API 401 — Your session is no longer valid. Sign in again.';
  if (error.status === 403)
    return 'API 403 — Your account does not have System Administrator access for this organization.';
  if (error.status === 404 && error.message === 'Not Found')
    return `API 404 — ${DEPLOYMENT_MISMATCH}`;
  if (error.status === 404) return `API 404 — ${fallback}`;
  if (error.status === 502) return `API 502 — ${error.message}`;
  if (error.status === 409 || error.status === 422)
    return `API ${String(error.status)} — ${error.message}`;
  if (error.status >= 500)
    return `API ${String(error.status)} — The administration service encountered an error. Retry shortly or inspect the backend logs.`;
  return fallback;
}
