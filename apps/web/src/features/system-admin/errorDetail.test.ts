import { describe, expect, it } from 'vitest';
import { ApiError } from '../../api/client';
import { systemAdminErrorDetail } from './errorDetail';

describe('systemAdminErrorDetail', () => {
  it.each([
    [
      new ApiError('Not Found', 404),
      'This API route is not available on the deployed backend.',
    ],
    [new ApiError('Forbidden', 403), 'does not have System Administrator'],
    [new ApiError('network detail', 0), 'could not be reached'],
    [new ApiError('internal detail', 500), 'encountered an error'],
    [
      new ApiError(
        'The server response is incompatible with this application version',
        502,
      ),
      'incompatible with this application version',
    ],
  ])('maps %o to a safe actionable message', (error, expected) => {
    expect(systemAdminErrorDetail(error)).toContain(expected);
  });

  it('preserves safe validation details from the API', () => {
    expect(
      systemAdminErrorDetail(new ApiError('Unknown department: finance', 422)),
    ).toBe('API 422 — Unknown department: finance');
  });
});
