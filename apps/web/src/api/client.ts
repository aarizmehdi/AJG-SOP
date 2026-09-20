import { z } from 'zod';

const appMode = import.meta.env.VITE_APP_MODE ?? 'fixture';
const rawApiUrl = import.meta.env.VITE_API_URL;
if (appMode === 'live' && !rawApiUrl) {
  throw new Error(
    'VITE_API_URL environment variable must be configured in live mode',
  );
}
const apiUrl = (rawApiUrl ?? 'http://localhost:8000/api/v1').replace(
  /\/+$/,
  '',
);

let accessTokenProvider: () => Promise<string | null> = () =>
  Promise.resolve(null);

export function configureAccessTokenProvider(
  provider: () => Promise<string | null>,
) {
  accessTokenProvider = provider;
}

async function authorizedHeaders(supplied?: HeadersInit) {
  const headers = new Headers(supplied);
  if ((import.meta.env.VITE_APP_MODE ?? 'fixture') === 'fixture') {
    const fixtureIdentity = window.localStorage.getItem('ajt-fixture-identity');
    if (!fixtureIdentity) throw new ApiError('Authentication required', 401);
    headers.set('Authorization', `Fixture ${fixtureIdentity}`);
  } else {
    try {
      const token = await accessTokenProvider();
      if (token) headers.set('Authorization', `Bearer ${token}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new ApiError(`Authentication token error: ${msg}`, 401);
    }
  }
  return headers;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function apiRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  const headers = await authorizedHeaders(init?.headers);
  if (!(init?.body instanceof FormData))
    headers.set('Content-Type', 'application/json');

  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, { ...init, headers });
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    throw new ApiError(
      `Cannot connect to API backend at ${apiUrl} (${errorMsg})`,
      0,
    );
  }

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = z.object({ detail: z.string() }).safeParse(body);
    throw new ApiError(
      detail.success ? detail.data.detail : 'Request failed',
      response.status,
    );
  }
  return schema.parse(await response.json());
}

export async function apiBlob(path: string): Promise<Blob> {
  const response = await fetch(`${apiUrl}${path}`, {
    headers: await authorizedHeaders(),
  });
  if (!response.ok)
    throw new ApiError('Source preview unavailable', response.status);
  return response.blob();
}
