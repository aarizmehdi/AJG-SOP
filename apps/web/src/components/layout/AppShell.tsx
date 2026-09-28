import {
  BookOpen,
  Library,
  MessageCircle,
  Search,
  ShieldCheck,
} from 'lucide-react';
import { NavLink, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { profileSchema } from '../../types/profile';
import { ProfileMenu } from './ProfileMenu';
import { AnimatedOutlet } from './AnimatedOutlet';
import { BrandMark } from '../ui/BrandMark';
import { useLanguage } from '../../features/language/useLanguage';

const links = [
  { to: '/home', key: 'home', icon: BookOpen },
  { to: '/search', key: 'searchNav', icon: Search },
  { to: '/assistant', key: 'assistantNav', icon: MessageCircle },
] as const;

export function AppShell() {
  const { t } = useLanguage();
  const location = useLocation();
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });
  const isAdmin =
    profile.data?.application_roles.some(
      (role) => role === 'sop_admin' || role === 'system_admin',
    ) ?? false;
  const isSystemAdmin =
    profile.data?.application_roles.includes('system_admin') ?? false;
  const visibleLinks = [
    ...links,
    ...(isAdmin
      ? [
          isSystemAdmin
            ? {
                to: '/admin/overview',
                key: 'systemAdminNav' as const,
                icon: ShieldCheck,
              }
            : {
                to: '/admin/policies',
                key: 'libraryNav' as const,
                icon: Library,
              },
        ]
      : []),
  ];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/home" className="brand" aria-label={t('brandName')}>
          <BrandMark compact />
          <span>
            <strong>{t('brandTitle')}</strong>
            <small>{t('brandName')}</small>
          </span>
        </NavLink>
        <nav
          className={isAdmin ? 'nav--admin' : undefined}
          aria-label={t('brandTitle')}
        >
          {visibleLinks.map(({ to, key, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `nav-link${
                  isActive ||
                  (to.startsWith('/admin') &&
                    location.pathname.startsWith('/admin'))
                    ? ' active'
                    : ''
                }`
              }
            >
              <Icon size={19} aria-hidden="true" />
              <span>{t(key)}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-profile">
          <ProfileMenu profile={profile.data} />
        </div>
      </aside>
      <div className="workspace">
        <div className="mobile-shell-bar">
          <NavLink to="/home" className="mobile-brand">
            <BrandMark compact />
            <strong>{t('brandTitle')}</strong>
          </NavLink>
          <ProfileMenu profile={profile.data} />
        </div>
        <AnimatedOutlet />
      </div>
    </div>
  );
}
