import { z } from 'zod';
import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('live API client', () => {
  it('sends the Firebase ID token as a bearer credential', async () => {
    vi.stubEnv('VITE_APP_MODE', 'live');
    vi.stubEnv('VITE_API_URL', 'https://api.example.test/api/v1');
    const request = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const { apiRequest, configureAccessTokenProvider } =
      await import('./client');
    configureAccessTokenProvider(() => Promise.resolve('firebase-id-token'));

    await apiRequest('/profile/me', z.object({ ok: z.boolean() }));

    const headers = new Headers(request.mock.calls[0]?.[1]?.headers);
    expect(request.mock.calls[0]?.[0]).toBe(
      'https://api.example.test/api/v1/profile/me',
    );
    expect(headers.get('Authorization')).toBe('Bearer firebase-id-token');
  });
});
