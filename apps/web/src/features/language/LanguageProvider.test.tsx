import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { configureAccessTokenProvider } from '../../api/client';
import type { Profile } from '../../types/profile';
import { LanguageProvider } from './LanguageProvider';
import { useLanguage } from './useLanguage';

const profile: Profile = {
  id: 'employee-one',
  organization_id: 'ajt',
  display_name: 'Ayesha Khan',
  email: 'ayesha@example.test',
  application_roles: ['employee'],
  departments: ['store'],
  locations: ['main'],
  organizational_roles: ['store_keeper'],
  management_departments: [],
  management_locations: [],
  management_roles: [],
  preferred_language: 'english',
  active: true,
  status: 'active',
  version: 1,
};

function Probe({ boundProfile = profile }: { boundProfile?: Profile }) {
  const locale = useLanguage();
  return (
    <>
      <output>
        {locale.language}:{locale.hasPreference.toString()}
      </output>
      <button
        onClick={() => {
          locale.bindProfile(boundProfile);
        }}
      >
        Bind first
      </button>
      <button
        onClick={() => {
          locale.bindProfile({ ...profile, id: 'employee-two' });
        }}
      >
        Bind second
      </button>
      {(['english', 'urdu', 'roman_urdu'] as const).map((selected) => (
        <button
          key={selected}
          onClick={() => {
            void locale.setLanguage(selected).catch(() => undefined);
          }}
        >
          {selected === 'roman_urdu' ? 'Save Roman Urdu' : `Save ${selected}`}
        </button>
      ))}
    </>
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  configureAccessTokenProvider(() => Promise.resolve(null));
});

describe('profile language preference', () => {
  it.each(['english', 'urdu', 'roman_urdu'] as const)(
    'saves %s through the authenticated self-service endpoint and restores it after login',
    async (selected) => {
      vi.stubEnv('VITE_APP_MODE', 'live');
      configureAccessTokenProvider(() => Promise.resolve('test-session'));
      const request = vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ preferred_language: selected }), {
            status: 200,
          }),
        ),
      );
      vi.stubGlobal('fetch', request);
      const first = render(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>,
      );
      fireEvent.click(screen.getByRole('button', { name: 'Bind first' }));
      const label =
        selected === 'roman_urdu' ? 'Save Roman Urdu' : `Save ${selected}`;
      fireEvent.click(screen.getByRole('button', { name: label }));
      await act(async () => {
        await Promise.resolve();
      });
      expect(await screen.findByText(`${selected}:true`)).toBeInTheDocument();
      expect(request).toHaveBeenCalledOnce();
      const [url, init] = request.mock.calls[0] as unknown as [
        string,
        RequestInit,
      ];
      expect(url).toContain(`/profile/language?language=${selected}`);
      expect(init.method).toBe('PUT');
      expect(new Headers(init.headers).get('Authorization')).toBe(
        'Bearer test-session',
      );
      expect(window.localStorage.getItem('ajt-language:ajt:employee-one')).toBe(
        selected,
      );
      first.unmount();
      window.localStorage.clear();
      render(
        <LanguageProvider>
          <Probe boundProfile={{ ...profile, preferred_language: selected }} />
        </LanguageProvider>,
      );
      fireEvent.click(screen.getByRole('button', { name: 'Bind first' }));
      expect(screen.getByText(`${selected}:true`)).toBeInTheDocument();
      expect(document.documentElement.dir).toBe(
        selected === 'urdu' ? 'rtl' : 'ltr',
      );
    },
  );

  it('uses the persisted live preference over a stale browser value', () => {
    vi.stubEnv('VITE_APP_MODE', 'live');
    window.localStorage.setItem('ajt-language:ajt:employee-one', 'english');
    render(
      <LanguageProvider>
        <Probe boundProfile={{ ...profile, preferred_language: 'urdu' }} />
      </LanguageProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Bind first' }));
    expect(screen.getByText('urdu:true')).toBeInTheDocument();
  });

  it('does not report a failed server save as a persisted preference', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    const request = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: 'Profile changed' }), {
          status: 409,
        }),
      ),
    );
    vi.stubGlobal('fetch', request);
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Bind first' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save Roman Urdu' }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(request).toHaveBeenCalledOnce();
    expect(screen.getByText('english:false')).toBeInTheDocument();
    expect(
      window.localStorage.getItem('ajt-language:ajt:employee-one'),
    ).toBeNull();
  });

  it('asks a first-time fixture employee, then scopes the saved preference to that profile', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ preferred_language: 'roman_urdu' }), {
            status: 200,
          }),
        ),
      ),
    );
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Bind first' }));
    });
    expect(screen.getByText('english:false')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Save Roman Urdu' }));
    expect(await screen.findByText('roman_urdu:true')).toBeInTheDocument();
    expect(window.localStorage.getItem('ajt-language:ajt:employee-one')).toBe(
      'roman_urdu',
    );
    expect(document.documentElement.dir).toBe('ltr');

    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Bind second' }));
    });
    expect(screen.getByText('english:false')).toBeInTheDocument();
  });
});
