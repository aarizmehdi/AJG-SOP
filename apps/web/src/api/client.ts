import { z } from 'zod';

const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1';
let accessTokenProvider: () => Promise<string | null> = () =>
  Promise.resolve(null);

export function configureAccessTokenProvider(
  provider: () => Promise<string | null>,
) {
  accessTokenProvider = provider;
}

async function authorizedHeaders(path: string, supplied?: HeadersInit) {
  const headers = new Headers(supplied);
  if ((import.meta.env.VITE_APP_MODE ?? 'fixture') === 'fixture') {
    const fixtureIdentity =
      window.localStorage.getItem('ajt-fixture-identity') ?? 'employee';
    headers.set('Authorization', `Fixture ${fixtureIdentity}`);
  } else {
    const token = await accessTokenProvider();
    if (token) headers.set('Authorization', `Bearer ${token}`);
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
  const headers = await authorizedHeaders(path, init?.headers);
  if (!(init?.body instanceof FormData))
    headers.set('Content-Type', 'application/json');
  const response = await fetch(`${apiUrl}${path}`, { ...init, headers });
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
    headers: await authorizedHeaders(path),
  });
  if (!response.ok)
    throw new ApiError('Source preview unavailable', response.status);
  return response.blob();
}
