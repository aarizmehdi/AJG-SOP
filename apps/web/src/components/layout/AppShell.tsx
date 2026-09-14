import { BookOpen, Library, MessageCircle, Search } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { profileSchema } from '../../types/profile';

const links = [
  { to: '/home', label: 'Home', icon: BookOpen },
  { to: '/search', label: 'Search SOPs', icon: Search },
  { to: '/assistant', label: 'SOP Assistant', icon: MessageCircle },
  { to: '/admin', label: 'Policy Library', icon: Library },
];

export function AppShell() {
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });
  const isAdmin =
    profile.data?.application_roles.some(
      (role) => role === 'sop_admin' || role === 'system_admin',
    ) ?? false;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink
          to="/home"
          className="brand"
          aria-label="Aziz Jan Trust SOP Knowledge home"
        >
          <img src="/brand/aziz-jan-trust-logo.png" alt="Aziz Jan Trust" />
          <span>
            <strong>SOP Knowledge</strong>
            <small>Aziz Jan Trust</small>
          </span>
        </NavLink>
        <nav aria-label="Main navigation">
          {links
            .filter((link) => link.to !== '/admin' || isAdmin)
            .map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `nav-link${isActive ? ' active' : ''}`
                }
              >
                <Icon size={19} aria-hidden="true" />
                <span>{label}</span>
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-foot">
          <span className="status-dot" />
          Secure {import.meta.env.VITE_APP_MODE ?? 'fixture'} workspace
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>{profile.data?.display_name ?? 'Aziz Jan Trust'}</span>
          <button className="avatar" aria-label="Open profile menu">
            {profile.data?.display_name
              .split(' ')
              .map((part) => part[0])
              .join('')
              .slice(0, 2) ?? 'AJ'}
          </button>
        </header>
        <Outlet />
      </div>
    </div>
  );
}
