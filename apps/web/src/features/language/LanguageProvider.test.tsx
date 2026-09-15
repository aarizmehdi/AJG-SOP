import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
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
  preferred_language: 'english',
};

function Probe() {
  const locale = useLanguage();
  return (
    <>
      <output>
        {locale.language}:{locale.hasPreference.toString()}
      </output>
      <button
        onClick={() => {
          locale.bindProfile(profile);
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
      <button
        onClick={() => {
          void locale.setLanguage('roman_urdu');
        }}
      >
        Save Roman Urdu
      </button>
    </>
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe('profile language preference', () => {
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
