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
    this.name = 'ApiError';
  }
}

function errorDetail(body: unknown): string {
  const parsed = z.object({ detail: z.unknown() }).safeParse(body);
  if (!parsed.success) return 'Request failed';
  if (typeof parsed.data.detail === 'string') return parsed.data.detail;
  if (!Array.isArray(parsed.data.detail)) return 'Request failed';
  const issues: unknown[] = parsed.data.detail as unknown[];
  const issue: unknown = issues.find(
    (value: unknown) =>
      z.object({ type: z.string(), loc: z.array(z.unknown()) }).safeParse(value)
        .success,
  );
  const validation = z
    .object({ type: z.string(), loc: z.array(z.unknown()) })
    .safeParse(issue);
  if (!validation.success) return 'Check the submitted fields and try again';
  const field = validation.data.loc
    .filter(
      (part): part is string =>
        typeof part === 'string' && /^[a-z_]+$/.test(part) && part !== 'body',
    )
    .join(' ')
    .replaceAll('_', ' ');
  const label = field
    ? `${field.charAt(0).toUpperCase()}${field.slice(1)}: `
    : '';
  const message: Record<string, string> = {
    missing: 'this field is required',
    too_short: 'at least one selection is required',
    string_too_short: 'enter a longer value',
    string_too_long: 'enter a shorter value',
    extra_forbidden: 'this field is not accepted',
    enum: 'select a supported value',
    literal_error: 'select a supported value',
  };
  return `${label}${message[validation.data.type] ?? 'check this value and try again'}`;
}

export async function apiStream(
  path: string,
  init: RequestInit,
): Promise<Response> {
  const headers = await authorizedHeaders(init.headers);
  headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'text/event-stream');
  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, { ...init, headers });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new ApiError('Cannot connect to the API backend', 0);
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw new ApiError(errorDetail(body), response.status);
  }
  if (!response.body)
    throw new ApiError('The response stream is unavailable', 502);
  return response;
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
    throw new ApiError(errorDetail(body), response.status);
  }
  const body: unknown = await response.json().catch(() => {
    throw new ApiError(
      'The API returned a response that could not be read',
      502,
    );
  });
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(
      'The server response is incompatible with this application version',
      502,
    );
  }
  return parsed.data;
}
