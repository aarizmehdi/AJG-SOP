import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { Profile } from '../../types/profile';
import { LanguageContext } from '../../features/language/language-context';
import { messages } from '../../features/language/messages';
import { ProfileMenu } from './ProfileMenu';

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

afterEach(() => {
  window.localStorage.clear();
});

describe('fixture profile menu', () => {
  it('supports keyboard focus, Escape, outside click, and a real logout', () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    render(
      <QueryClientProvider client={new QueryClient()}>
        <LanguageContext
          value={{
            language: 'english',
            hasPreference: true,
            profileId: profile.id,
            bindProfile: () => {},
            setLanguage: async () => {},
            t: (key) => messages.english[key],
          }}
        >
          <MemoryRouter initialEntries={['/']}>
            <Routes>
              <Route
                path="/"
                element={
                  <>
                    <ProfileMenu profile={profile} />
                    <button>Outside</button>
                  </>
                }
              />
              <Route path="/login" element={<p>Login destination</p>} />
            </Routes>
          </MemoryRouter>
        </LanguageContext>
      </QueryClientProvider>,
    );
    const trigger = screen.getByRole('button', { name: 'Profile' });
    fireEvent.click(trigger);
    expect(screen.getByText('ayesha@example.test')).toBeInTheDocument();
    const language = screen.getByRole('menuitem', { name: /Language/ });
    const logout = screen.getByRole('menuitem', { name: 'Logout' });
    expect(language).toHaveFocus();
    fireEvent.keyDown(language, { key: 'ArrowDown' });
    expect(logout).toHaveFocus();
    fireEvent.keyDown(logout, { key: 'Escape' });
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();

    fireEvent.click(trigger);
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Outside' }));
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();

    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Logout' }));
    expect(window.localStorage.getItem('ajt-fixture-identity')).toBeNull();
    expect(screen.getByText('Login destination')).toBeInTheDocument();
  });
});
